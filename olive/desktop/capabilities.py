"""Temporary accessibility capabilities. These are observations, not permissions."""

def capability_map(observation):
    result = []
    for control in observation.get("controls", [])[:300]:
        if control.get("password") or not control.get("enabled") or not control.get("visible"):
            continue
        actions = list(control.get("actions", []))
        if actions:
            result.append({"target": {key: control.get(key, "") for key in
                                     ("runtime_id", "name", "control_type", "automation_id")},
                           "actions": actions, "untrusted_content": True})
    return result
