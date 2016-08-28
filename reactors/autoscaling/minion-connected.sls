{% if data['act']=='pend' and data['id'].startswith('PLACEHOLDER_MINION_PREFIX-') %}
register_minion_if_autoscaling_instance:
  runner.autoscaling.minion_connected:
    - name: {{ data['id'] }}
{% endif %}
