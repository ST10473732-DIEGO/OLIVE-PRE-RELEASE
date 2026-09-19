from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Feature:
    id: str
    title: str
    description: str
    icon: str = "SP_FileIcon"
    singleton: bool = True
    enabled: bool = True
    priority: int = 10
    badge: str = ""
    shortcut: str = ""
    window_type: str = "workspace"
    factory: Callable[[Any], Any] | None = None


class FeatureRegistry:
    def __init__(self):
        self.features = {}

    def register(self, feature):
        if feature.id in self.features:
            raise ValueError(f"Duplicate feature: {feature.id}")
        self.features[feature.id] = feature

    def list(self):
        return sorted((f for f in self.features.values() if f.enabled), key=lambda f: f.priority)

    def get(self, feature_id):
        feature = self.features[feature_id]
        if not feature.enabled:
            raise PermissionError("Feature is disabled")
        return feature


def default_registry():
    registry = FeatureRegistry()
    for priority, (name, description, icon) in enumerate(
        [
            ("Home", "Your local AI workspace", "SP_ComputerIcon"),
            ("Chat", "Think, write and explore with local models", "SP_FileDialogDetailedView"),
            ("Agent", "Plan and carry out approved tasks", "SP_MediaPlay"),
            ("Studio", "Build, edit and test local projects", "SP_DesktopIcon"),
            ("Research", "Investigate questions with current sources and evidence", "SP_FileDialogContentsView"),
            ("Desktop", "Inspect and control authorized Windows applications", "SP_ComputerIcon"),
            ("Projects", "Keep your work and context together", "SP_DirIcon"),
            ("Knowledge", "Find answers in your local documents", "SP_FileDialogContentsView"),
            ("Memory", "Review what OLIVE remembers", "SP_DialogSaveButton"),
            ("Settings", "Make OLIVE your own", "SP_FileDialogInfoView"),
            ("Diagnostics", "Inspect local runtime health", "SP_MessageBoxInformation"),
        ]
    ):
        registry.register(
            Feature(
                name.lower(), "Desktop Control" if name == "Desktop" else name, description, icon, priority=90 + priority if name in {"Settings", "Diagnostics"} else priority
            )
        )
    return registry
