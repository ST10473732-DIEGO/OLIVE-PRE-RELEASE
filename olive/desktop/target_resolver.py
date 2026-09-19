"""Exact semantic resolution; ambiguous matches never become clicks."""

import re
from .models import ControlTarget


def normalized(value):
    return re.sub(r"\s+", " ", str(value).casefold().strip().lstrip("#")).replace("&", "")


class AmbiguousTarget(ValueError):
    pass


class DesktopTargetResolver:
    def resolve(self, controls, target):
        if isinstance(target, dict):
            target = ControlTarget(**target)
        if not any((target.name, target.automation_id, target.runtime_id, target.control_type)):
            raise ValueError("Specify a semantic target")
        matches = []
        for control in controls:
            if not control.get("enabled", True) or not control.get("visible", True):
                continue
            if target.runtime_id and target.runtime_id != control.get("runtime_id"):
                continue
            if target.automation_id and target.automation_id != control.get("automation_id"):
                continue
            if target.control_type and normalized(target.control_type) != normalized(control.get("control_type")):
                continue
            if target.parent_id and target.parent_id != control.get("parent_id"):
                continue
            if target.name and normalized(target.name) != normalized(control.get("name")):
                continue
            matches.append(control)
        if len(matches) > 1:
            raise AmbiguousTarget("Several controls match; specify automation ID or hierarchy")
        if not matches:
            raise LookupError("No accessible control matches the target")
        return matches[0]
