"""Recognise an explicit request to create a real project OLIVE should build.

Pure functions over the literal local request; a model never supplies this.
"Write me a Python script" stays an answer in Chat. A request becomes a
workspace task only when it names a project/workspace or asks OLIVE to build,
run or show the result ("...and show me it", "Build it, run it").
"""
from pathlib import Path
import re

from .deliverable import instruction_text

_CREATE = r"^(?:please\s+|(?:can|could|would) you\s+)?(?:create|make|build|generate|scaffold|set up|start)\s+(?:me\s+|us\s+)?(?:a|an|the|my)?\s*"
_WEB = re.compile(r"\b(?:web ?sites?|web ?pages?|landing ?pages?|home ?pages?|html (?:page|site)|static (?:site|page)|portfolio (?:site|page))\b")
_ASPNET = re.compile(r"\b(?:asp\.?\s?net(?:\s+core)?(?:\s+(?:web\s+)?api)?|\.net\s+(?:web\s+)?api|(?:c#|csharp)\s+(?:web\s+)?api)\b")
_LANGUAGES = (("csharp", r"c#|csharp|\.net"), ("javascript", r"javascript|node(?:\.js)?"),
              ("java", r"java(?!script)"), ("python", r"python"))
_SOFTWARE = r"\b(?:project|app|application|program|tool|cli|api|service|script)\b"
_EXPLICIT_PROJECT = re.compile(r"\b(?:project|workspace|in (?:olive )?studio)\b")
_RUN = re.compile(r"\b(?:run|start|launch|serve|host) (?:it|them|the (?:app|site|api|server|project|page))\b|\bbuild (?:it|and run)\b|\brun it\b")
_SHOW = re.compile(r"\b(?:show|let) (?:me|us)\b|\bpreview\b|\bwhat it looks like\b|\bopen (?:it|the (?:site|page|preview))\b")
_TEST = re.compile(r"\b(?:run|execute) (?:the |its )?tests?\b|\btest it\b")
DEFAULT_NAMES = {"web": "OliveSite", "aspnet": "OliveApi"}
NAME = re.compile(r"\b(?:called|named|name it)\s+[\"'“]?([A-Za-z][A-Za-z0-9_-]{0,79})")


def project_request(text):
    """Return a creation spec, or None when the literal request is not a project task."""
    if not isinstance(text, str) or len(text) > 4000:
        return None
    value = instruction_text(text)
    value = re.sub(r"```.*?(?:```|$)", " ", value, flags=re.S)
    negated = " ".join(re.findall(r"\b(?:do not|don't|never|without)\s+([^.;,\n]+)", value))
    positive = re.sub(r"\b(?:do not|don't|never|without)\s+[^.;,\n]+", " ", value)
    if not re.match(_CREATE, positive):
        return None
    kind = "web" if _WEB.search(positive) else "aspnet" if _ASPNET.search(positive) else ""
    language = ""
    if not kind:
        for name, pattern in _LANGUAGES:
            if re.search(r"(?:^|[\s(])(?:" + pattern + r")(?=$|[\s,.)])", positive) and re.search(_SOFTWARE, positive):
                language = name
                break
        if not language:
            return None
    run = bool(_RUN.search(positive)) and not re.search(r"\b(?:run|start|launch)\b", negated)
    show = bool(_SHOW.search(positive)) and not re.search(r"\b(?:show|preview|open)\b", negated)
    tests = bool(_TEST.search(positive)) and not re.search(r"\btests?\b", negated)
    build = bool(re.search(r"\bbuild (?:it|and)\b|\bcompile\b", positive))
    # Being a creation phrase is not enough for general code: the user must ask
    # for a real project/workspace, or ask OLIVE to build, run, test or show the
    # result. A website or ASP.NET API is only meaningful as a running project.
    if not (_EXPLICIT_PROJECT.search(positive) or run or show or tests or build or kind):
        return None
    name = NAME.search(text)
    if kind == "web":
        spec = {"language": "web", "template": "static"}
    elif kind == "aspnet":
        spec = {"language": "csharp", "template": "webapi"}
    else:
        spec = {"language": language, "template": "console"}
    # A website is shown by default (that is what one is for) unless declined.
    declined = bool(re.search(r"\b(?:run|start|show|preview|open|launch|serve)\b", negated))
    preview = show or (run and kind in {"web", "aspnet"}) or (kind == "web" and not declined)
    spec.update(kind=kind or language, name=name.group(1) if name else "", run=run or preview, preview=preview,
                tests=tests, build=build or run or tests)
    return spec


def resolve_name(spec, location):
    """The explicit name, or the first unused default name. Never an existing folder."""
    if spec["name"]:
        return spec["name"]
    base = DEFAULT_NAMES.get(spec["kind"], "OliveApp")
    root = Path(location)
    for index in range(1, 1000):
        candidate = base if index == 1 else f"{base}{index}"
        if not (root / candidate).exists():
            return candidate
    raise ValueError("Choose a project name; the default names are all in use.")
