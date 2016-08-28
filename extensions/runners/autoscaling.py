"""Runner that implements autoaccepting autoscaled minions.

Not necessarily AWS specific. Note that this runner must not be used
concurrently as sqlite doesn't really like that.
"""
import salt.client
import subprocess


# Constants

DEFAULT_DATABASE_LOCATION = '/var/tmp/salt-autoscaling.db'
DEFAULT_REGISTRY_SCRIPT = '/PLACEHOLDER_PATH_TO_REACTORS/autoscaling/autoscale_registry.py'


# Functions


def _registry_call(database_location, registry_script):
  return ['python', registry_script, '--database-file', database_location]


def _accept_minion(name):
  wheel = salt.wheel.Wheel(__opts__)
  wheel.call_func('key.accept', match=name)
  print "Accepted minion:", name


def _key_submitted_and_autoscaled(registry_call, name):
  return subprocess.call(registry_call + ['check', name]) == 0


def minion_connected(name, database_location=DEFAULT_DATABASE_LOCATION,
    registry_script=DEFAULT_REGISTRY_SCRIPT):
  """
  Notify that a potential autoscaling minion has connected.
  
  If a minion with the same name has been registered through
  `register_autoscaled_instance` function, the minion will automatically be accepted.
  """
  registry_call = _registry_call(database_location, registry_script)
  subprocess.call(registry_call + ['new-minion', name])
  if _key_submitted_and_autoscaled(registry_call, name):
    _accept_minion(name)


def register_autoscaled_instance(name,
    database_location=DEFAULT_DATABASE_LOCATION,
    registry_script=DEFAULT_REGISTRY_SCRIPT):
  """
  Notify that an autoscaling instance has started and we should accept it.
  
  If the minion has previously been submitted to `minion_connected`, the minion
  will be accepted immediately.
  """
  registry_call = _registry_call(database_location, registry_script)
  subprocess.call(registry_call + ['new-instance', name])
  if _key_submitted_and_autoscaled(registry_call, name):
    _accept_minion(name)


def highstate_accepted_minion(name,
    database_location=DEFAULT_DATABASE_LOCATION,
    registry_script=DEFAULT_REGISTRY_SCRIPT):
  """
  Highstate a previously accepted minion.

  Highstating is done asynchronously to not block the reactor.
  """
  registry_call = _registry_call(database_location, registry_script)
  if _key_submitted_and_autoscaled(registry_call, name):
    client = salt.client.LocalClient(__opts__['conf_file'])
    client.cmd_async(name, 'state.highstate')


def tag_aws_instance(resourceid, name):
  # Assumes either the runner host has an EC2 role assigned to it, or it has
  # AWS credentials in its user's home directory.
  subprocess.call(['aws', 'ec2', 'create-tags', '--resources', resourceid,
    '--tags', 'Key=Name,Value={0}'.format(name)])
