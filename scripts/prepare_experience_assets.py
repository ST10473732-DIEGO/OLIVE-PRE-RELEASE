"""Package the approved-source derivative and OLIVE's original vector icon family.

The original artwork is never modified. Transparency extraction is a separate,
reviewable image-generation step; this script only sizes and packages that result.
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "home": '<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z"/>',
    "chat": '<path d="M4 4h16v12H9l-5 4Z"/><path d="M8 8h8M8 12h5"/>',
    "agent": '<path d="M5 5h14v14H5Z"/><path d="m10 8 5 4-5 4Z"/>',
    "studio": '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 20"/>',
    "research": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6m-3-3v6"/>',
    "desktop": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    "projects": '<path d="M3 6h7l2 3h9v12H3Z"/>',
    "knowledge": '<path d="M12 5C8 3 5 3 2 4v15c3-1 6-1 10 1 4-2 7-2 10-1V4c-3-1-6-1-10 1Zm0 0v15"/>',
    "memory": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
    "diagnostics": '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
}


def main():
    tokens = json.loads((ROOT / "olive/ui_qt/experience/tokens.json").read_text())
    for theme in ("dark", "light"):
        folder = ROOT / "assets/icons" / theme
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in PATHS.items():
            (folder / f"{name}.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                f'stroke="{tokens[theme]["text"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{content}</svg>', encoding="utf-8")
    branding = ROOT / "assets/branding"
    candidate = Image.open(branding / "olive-transparent-candidate.png").convert("RGBA")
    if candidate.getchannel("A").getextrema() != (0, 255):
        raise ValueError("The derivative must have genuine transparency")
    subject = candidate.crop(candidate.getbbox())
    master = Image.new("RGBA", (256, 256))
    subject.thumbnail((224, 224), Image.Resampling.LANCZOS)
    master.alpha_composite(subject, ((256-subject.width)//2, (256-subject.height)//2))
    sizes = (16, 24, 32, 48, 64, 128, 256)
    for size in sizes:
        master.resize((size, size), Image.Resampling.LANCZOS).save(branding / f"olive-{size}.png")
    master.save(branding / "olive.ico", sizes=[(s, s) for s in sizes])


if __name__ == "__main__":
    main()
