from __future__ import annotations

THEMES = {
    "OLIVE Blue": {
        "bg": "#0b1118",
        "surface": "#121a24",
        "surface2": "#1a2532",
        "border": "#2a3949",
        "accent": "#4da3ff",
        "text": "#e6edf3",
        "text_secondary": "#93a4b5",
        "success": "#3fb950",
        "danger": "#f85149",
        "warning": "#d29922",
    },
    "True Black": {
        "bg": "#000000",
        "surface": "#101010",
        "surface2": "#191919",
        "border": "#333333",
        "accent": "#4da3ff",
        "text": "#f0f0f0",
        "text_secondary": "#999999",
        "success": "#45c46b",
        "danger": "#ff5c5c",
        "warning": "#e0ad3a",
    },
    "Deep Purple": {
        "bg": "#100b1d",
        "surface": "#19122b",
        "surface2": "#241a3b",
        "border": "#3b2d59",
        "accent": "#a78bfa",
        "text": "#eee8ff",
        "text_secondary": "#b8a9db",
        "success": "#5ecb8a",
        "danger": "#ff6b7a",
        "warning": "#e6b94d",
    },
    "Ocean Dark": {
        "bg": "#07131f",
        "surface": "#0d2233",
        "surface2": "#15334a",
        "border": "#27506d",
        "accent": "#4fc3f7",
        "text": "#e8f5ff",
        "text_secondary": "#91b9cf",
        "success": "#4ac78e",
        "danger": "#ff6678",
        "warning": "#e0b24a",
    },
}

DEFAULT_THEME = "OLIVE Blue"


def get_theme(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES[DEFAULT_THEME]).copy()
