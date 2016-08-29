"""A small CLI application for tracking autoscaling of minions.

For a minion to be auto-accepted by a Salt master there are two separate events that needs to happen:

  1. new-instance: The autoscaling group must have published that minion will
     connect.
  2. new-minion: The minion must have connected to the master.

When both requirements are satisfied (check), a minion can be accepted. This
script keeps a small sqlite database of the auto-scaling states minions are in.

TODO: Add a pruning command to eventually delete old data.
"""
import argparse
import collections
import contextlib
import datetime
import os
import sqlite3
import sys
import time


def pid_is_running(pid):
  """Check For the existence of a unix pid. """
  try:
    os.kill(pid, 0)
  except OSError:
    return False
  else: return True


class InterprocessLock:
  def __init__(self, path, timeout):
    self._path = path
    self._timeout = timeout   # seconds

  def _try_lock_once(self):
    try:
      f = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_TRUNC)
      try:
        os.write(f, "{0}".format(os.getpid()))
      finally:
        os.close(f)
      return True
    except OSError, e:
      return False

  def _lock_owner_alive(self):
    try:
      f = open(self._path)
      with contextlib.closing(f):
        return pid_is_running(int(f.read()))
    except ValueError:
      return False
    except IOError:
      return False

  def _invalidate_lock(self):
    os.unlink(self._path)

  def _try_lock_with_retry(self):
    for _ in range(self._timeout):
      if self._try_lock_once():
        return True
      elif not self._lock_owner_alive():
        self._invalidate_lock()
      else:
        time.sleep(1)
    return False

  def try_lock(self):
    self._locked = self._try_lock_with_retry()
    return self._locked

  def close(self):
    if self._locked:
      self._invalidate_lock()


@contextlib.contextmanager
def sqlite_connection(path):
  conn = sqlite3.connect(path)
  yield conn
  conn.close()


@contextlib.contextmanager
def sqlite_cursor(conn):
  c = conn.cursor()
  yield c
  c.close()


Record = collections.namedtuple('Record', ('instanceid', 'instancetimestamp', 'miniontimestamp'))


def create_table_if_not_exist(conn):
  with sqlite_cursor(conn) as c:
    c.execute("CREATE TABLE IF NOT EXISTS instances (instanceid TEXT CONSTRAINT instanceid PRIMARY KEY ON CONFLICT REPLACE, instancetimestamp NUMERIC, miniontimestamp NUMERIC)")


def read_record(conn, instanceid):
  with sqlite_cursor(conn) as c:
    c.execute("SELECT instanceid, instancetimestamp, miniontimestamp FROM instances WHERE instanceid=?", (instanceid,))
    for row in c:
      return Record(*row)
    else:
      return None


def write_record(conn, record):
  with sqlite_cursor(conn) as c:
    c.execute("INSERT INTO instances (instanceid, instancetimestamp, miniontimestamp) VALUES(?, ?, ?)", record)


def new_instance(args):
  lock = InterprocessLock("{0}.lock".format(args.database_file), args.lock_timeout)
  if not lock.try_lock():
    print "Could not take lock."
    return 1

  with contextlib.closing(lock), sqlite_connection(args.database_file) as conn:
    create_table_if_not_exist(conn)
    for instance in args.instances:
      record = read_record(conn, instance)
      if record is None:
        record = Record(instanceid=instance, instancetimestamp=time.time(), miniontimestamp=None)
      else:
        record = record._replace(instancetimestamp=time.time())
      write_record(conn, record)
    conn.commit()
  return 0


def new_minion(args):
  lock = InterprocessLock("{0}.lock".format(args.database_file), args.lock_timeout)
  if not lock.try_lock():
    print "Could not take lock."
    return 1

  with contextlib.closing(lock), sqlite_connection(args.database_file) as conn:
    create_table_if_not_exist(conn)
    for minion in args.minions:
      record = read_record(conn, minion)
      if record is None:
        record = Record(instanceid=minion, instancetimestamp=None, miniontimestamp=time.time())
      else:
        record = record._replace(miniontimestamp=time.time())
      write_record(conn, record)
    conn.commit()
  return 0


def check(args):
  lock = InterprocessLock("{0}.lock".format(args.database_file), args.lock_timeout)
  if not lock.try_lock():
    print "Could not take lock."
    return 1

  with contextlib.closing(lock), sqlite_connection(args.database_file) as conn:
    create_table_if_not_exist(conn)
    with sqlite_cursor(conn) as c:
      c.execute("SELECT instanceid FROM instances"
                " WHERE miniontimestamp IS NULL AND instancetimestamp IS NOT NULL")
      for row in c:
        print "Pending instance registered as minion, but not as EC2 instance: {0}".format(row[0])
      c.execute("SELECT instanceid FROM instances"
                " WHERE miniontimestamp IS NOT NULL"
                " AND instancetimestamp IS NULL")
      for row in c:
        print "Pending instance registered as EC2 instance, but not as minion: {0}".format(row[0])

      c.execute("SELECT COUNT(*) FROM instances "
                "WHERE miniontimestamp IS NOT NULL"
                " AND instancetimestamp IS NOT NULL AND instanceid=?",
          (args.instance,))
      found = c.fetchone()[0] > 0

  if found:
    print "The minion can be accepted."
    return 0
  else:
    print "The minion is NOT ready for acceptance."
    return 1


def purge(args):
  lock = InterprocessLock("{0}.lock".format(args.database_file), args.lock_timeout)
  if not lock.try_lock():
    print "Could not take lock."
    return 1

  duration = datetime.timedelta(**{args.unit[0]: args.duration[0]}).total_seconds()
  purge_older_than = time.time() - duration

  with contextlib.closing(lock), sqlite_connection(args.database_file) as conn:
    create_table_if_not_exist(conn)
    with sqlite_cursor(conn) as c:
      c.execute("DELETE FROM instances"
          " WHERE (miniontimestamp < ? or miniontimestamp IS NULL)"
          " AND (instancetimestamp < ? or instancetimestamp IS NULL)",
          (purge_older_than, purge_older_than,))
      print "Deleted", c.rowcount, "rows."
      conn.commit()
  

def main(args):
  parser = argparse.ArgumentParser(description='A small database of minions to be accepted.')
  parser.add_argument('--database-file', default='autoscaling.db',
      help='sqlite3 database where where data is stored.')
  parser.add_argument('--lock-timeout', metavar='SECONDS', default=30, type=int,
      help='number of seconds to wait for exclusive database lock')

  subparsers = parser.add_subparsers(help='subcommand')

  new_instance_parser = subparsers.add_parser('new-instance',
      help='register a new instance started')
  new_instance_parser.add_argument('instances', nargs='+', metavar='INSTANCE',
      help='instance(s) to be added')
  new_instance_parser.set_defaults(func=new_instance)

  new_minion_parser = subparsers.add_parser('new-minion',
      help='register a new minion registered')
  new_minion_parser.add_argument('minions', nargs='+', metavar='MINION',
      help='minion(s) to be added')
  new_minion_parser.set_defaults(func=new_minion)

  purge_parser = subparsers.add_parser('purge',
      help='purge older records from the database')
  purge_parser.add_argument('duration', nargs=1, metavar='DURATION', type=int,
      help='time duration')
  purge_parser.add_argument('unit', nargs=1, metavar='UNIT',
      choices=('seconds', 'minutes','hours', 'days', 'weeks'), default='days',
      help='minion(s) to be added')
  purge_parser.set_defaults(func=purge)

  check_parser = subparsers.add_parser('check', help=('check if instance is'
      ' registered both in EC2 and Salt. This is to avoid autoaccepting minions'
      ' not in autoscaling groups. Also logs pending minions. Returns 0 if'
      ' instance is not pending, 1 otherwise.'))
  check_parser.add_argument('instance', metavar='INSTANCE',
      help='minion(s) to be added')
  check_parser.set_defaults(func=check)
  
  args = parser.parse_args()
  return args.func(args)


if __name__=='__main__':
  sys.exit(main(sys.argv))
