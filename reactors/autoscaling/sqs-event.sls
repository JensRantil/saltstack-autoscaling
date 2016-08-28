{% set minionid = "PLACEHOLDER_MINION_PREFIX-" + data['message']['Message']['EC2InstanceId'] %}


{% if data['message']['Message']['Event'] == "autoscaling:EC2_INSTANCE_LAUNCH" %}
set_autoscaled_instance_tag:
  runner.autoscaling.tag_aws_instance:
    - resourceid: {{ data['message']['Message']['EC2InstanceId'] }}
    - name: {{ minionid }}

accept_minion_if_pending:
  runner.autoscaling.register_autoscaled_instance:
    - name: {{ minionid }}
{% endif %}


{% if data['message']['Message']['Event'] == "autoscaling:EC2_INSTANCE_TERMINATE" %}
delete_minion_key:
  wheel.key.delete:
    - match: {{ minionid }}
{% endif %}
