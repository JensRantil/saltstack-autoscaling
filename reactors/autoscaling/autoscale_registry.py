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
import sys
import contextlib
import sqlite3
import time
import collections

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
  with sqlite_connection(args.database_file) as conn:
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
  with sqlite_connection(args.database_file) as conn:
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
  with sqlite_connection(args.database_file) as conn:
    create_table_if_not_exist(conn)
    with sqlite_cursor(conn) as c:
      c.execute("SELECT instanceid FROM instances"
                " WHERE miniontimestamp IS NULL AND instancetimestamp IS NOT NULL")
      for row in c:
        print "Pending instance registered as minion, but not as EC2 instance: {0}".format(row[0])
      c.execute("SELECT instanceid FROM instances"
                " WHERE miniontimestamp IS NOT NULL AND instancetimestamp IS NULL")
      for row in c:
        print "Pending instance registered as EC2 instance, but not as minion: {0}".format(row[0])

      c.execute("SELECT COUNT(*) FROM instances "
                "WHERE miniontimestamp IS NOT NULL AND instancetimestamp IS NOT NULL AND instanceid=?",
          (args.instance,))
      found = c.fetchone()[0] > 0

  if found:
    print "The minion can be accepted."
    return 0
  else:
    print "The minion is NOT ready for acceptance."
    return 1

  

def main(args):
  parser = argparse.ArgumentParser(description='A small database of minions to be accepted.')
  parser.add_argument('--database-file', default='autoscaling.db',
      help='sqlite3 database where where data is stored.')

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
