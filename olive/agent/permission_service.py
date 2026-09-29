from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..storage.json_store import JsonStore


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionEvaluation:
    decision: PermissionDecision
    permission: str
    scope: str | None
    reason: str


class PermissionService:
    DEFAULTS = {"filesystem.read": "ask", "filesystem.write": "ask", "filesystem.delete": "ask",
                "terminal.execute": "ask", "terminal.admin": "ask", "system.open_application": "ask",
                "system.close_application": "ask", "system.terminate_application": "ask",
                "desktop.view_screen":"deny", "desktop.inspect_application":"ask", "desktop.control_application":"ask",
                "desktop.keyboard_input":"deny", "desktop.mouse_input":"deny", "communication.send":"ask",
                "app.discord.read":"deny", "app.discord.navigate":"deny", "app.discord.send_message":"ask",
                "app.spotify.control":"ask", "network.search":"ask", "network.read":"ask",
                "network.download":"ask", "knowledge.write":"ask",
                "clipboard.read":"ask", "clipboard.write":"ask",
                "software.install":"ask", "software.purchase":"ask",
                "application.upload":"ask", "application.delete":"ask",
                "application.submit":"ask", "application.security_settings":"ask", "system.settings":"ask"}
    DEFAULTS.update({"app.file_explorer.navigate": "ask", "app.windows_settings.navigate": "ask", "application.media": "ask", "application.search": "ask"})
    DEFAULTS.update({f'{domain}.{action}': 'allow' if action=='read' else 'ask'
                     for domain in ('profile','contacts','calendar','tasks','reminders','personal')
                     for action in ('read','write','delete','merge','import','export')})
    # OLIVE Notes: literal Chat requests may read and edit (reversible, with history);
    # moving to Recently Deleted asks; permanent deletion always confirms.
    DEFAULTS.update({'notes.read': 'allow', 'notes.write': 'allow', 'notes.delete': 'ask'})
    DEFAULTS.update({f'mail.{action}':'allow' if action=='read' else 'ask'
                     for action in ('read','draft','modify','import','export','send','connect','connections','credentials','remote_modify')})

    def __init__(self, path: Path): self.store = JsonStore(path)

    @staticmethod
    def evaluate_device(rules: list[dict], capability: str, scope: str | None = None) -> PermissionDecision:
        """Connect uses exact opaque scopes, never local path/application trust.

        Missing device grants default to Off (DENY). More specific exact scopes
        override a device-wide rule; conflicting equal scopes fail closed.
        """
        matching = [r for r in rules if r['capability'] == capability and r['scope'] == scope]
        if not matching and scope is not None:
            matching = [r for r in rules if r['capability'] == capability and r['scope'] is None]
        decisions = {PermissionDecision(r['decision']) for r in matching}
        if not decisions or PermissionDecision.DENY in decisions:
            return PermissionDecision.DENY
        return PermissionDecision.ASK if PermissionDecision.ASK in decisions else PermissionDecision.ALLOW

    def policies(self) -> dict:
        value = self.store.read({"schema_version": 1, "permissions": {}, "scopes": [], "trusted_actions": []})
        if not isinstance(value, dict): value = {"schema_version": 1, "permissions": {}, "scopes": []}
        value.setdefault("permissions", {}); value.setdefault("scopes", []); value.setdefault("trusted_actions", [])
        return value

    def save(self, permissions: dict[str, str], scopes: list[dict] | None = None,
             trusted_actions: list[dict] | None = None) -> None:
        for decision in permissions.values(): PermissionDecision(decision)
        current = self.policies()
        self.store.write({"schema_version": 1, "permissions": permissions, "scopes": scopes or [],
                          "trusted_actions": current["trusted_actions"] if trusted_actions is None else trusted_actions})

    def trust_action(self, tool_name: str, target: str) -> None:
        value = self.policies(); key = {"tool":tool_name, "target":_normalize_action_target(target)}
        if key not in value["trusted_actions"]: value["trusted_actions"].append(key)
        self.save(value["permissions"], value["scopes"], value["trusted_actions"])

    def is_action_trusted(self, tool_name: str, target: str | None) -> bool:
        if not target: return False
        key = {"tool":tool_name, "target":_normalize_action_target(target)}
        all_targets = {"tool":tool_name, "target":"*"}
        return key in self.policies()["trusted_actions"] or all_targets in self.policies()["trusted_actions"]

    def clear_trusted_actions(self) -> int:
        value = self.policies(); count = len(value["trusted_actions"])
        self.save(value["permissions"], value["scopes"], [])
        return count

    def evaluate(self, permission: str, target: str | None = None, *, application: str | None = None) -> PermissionEvaluation:
        policies = self.policies()
        matching = []
        if application:
            matching.extend(((0, 1), application, rule.get("decision", "ask")) for rule in policies["scopes"]
                            if rule.get("permission") == permission and rule.get("application") == application
                            and not rule.get("path"))
        if target:
            normalized = _normalize_path(target)
            for rule in policies["scopes"]:
                if rule.get("permission") != permission or not rule.get("path"): continue
                if rule.get("application") and rule["application"] != application: continue
                scope = _normalize_path(rule["path"])
                try:
                    normalized.relative_to(scope)
                    matching.append(((len(str(scope)), bool(rule.get("application"))), scope, rule.get("decision", "ask")))
                except ValueError: pass
        if matching:
            specificity = max(item[0] for item in matching)
            selected = [item for item in matching if item[0] == specificity]
            decisions = {PermissionDecision(item[2]) for item in selected}
            decision = (PermissionDecision.DENY if PermissionDecision.DENY in decisions else
                        PermissionDecision.ASK if PermissionDecision.ASK in decisions else PermissionDecision.ALLOW)
            return PermissionEvaluation(decision, permission, str(selected[0][1]), "Most specific applicable scope")
        decision = policies["permissions"].get(permission, self.DEFAULTS.get(permission, "deny"))
        return PermissionEvaluation(PermissionDecision(decision), permission, None, "Permission policy")


def _normalize_path(value: str) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _normalize_action_target(value: str) -> str:
    return " ".join(value.strip().casefold().removesuffix(".exe").split())
