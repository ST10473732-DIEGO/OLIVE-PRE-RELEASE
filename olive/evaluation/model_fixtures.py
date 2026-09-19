"""Repeatable model fixtures. Generated code and tools are never executed."""

GENERAL = [
    ("simple_qa", "Return JSON with answer: how many minutes are in two hours?", {"answer": 120}),
    ("reasoning", "Ana is older than Ben. Ben is older than Cara. Return JSON with youngest.", {"youngest": "Cara"}),
    ("research_plan", "Choose the first safe research step for current documentation: search, shell, or send. Return JSON with action.", {"action": "search"}),
    ("tool_selection", "To inspect a window without typing, select inspect, type, or click. Return JSON with action.", {"action": "inspect"}),
]
CODING = [
    ("bug_location", "math.py contains def add(a,b): return a-b. ui.py displays results. Test add(2,3)==5 fails. Return JSON with file and operator to repair add.", {"file": "math.py", "operator": "+"}),
    ("targeted_change", "def clamp_zero(x): return min(0,x). Expected clamp_zero(-2)=0 and clamp_zero(3)=3. Return JSON with replacement_function, either min or max.", {"replacement_function": "max"}),
    ("test_failure", "Test expected 5 but received -1 for add(2,3). Return JSON with diagnosis, either subtraction or timeout.", {"diagnosis": "subtraction"}),
    ("strict_plan", "Before repairing math.py select first=read_file and second=edit_file. Return JSON with first and second only.", {"first": "read_file", "second": "edit_file"}),
]
TOOL_FIXTURE = ("tool_call", "Use inspect_window to inspect Notepad. Do not type or click.",
                {"name": "inspect_window", "application": "Notepad"})
TOOL_SCHEMA = [{"type": "function", "function": {"name": "inspect_window", "description": "Read a window",
    "parameters": {"type": "object", "properties": {"application": {"type": "string"}},
                   "required": ["application"], "additionalProperties": False}}}]


def schema(expected):
    return {"type": "object", "additionalProperties": False, "required": list(expected),
            "properties": {key: {"type": "integer" if type(value) is int else "string"}
                           for key, value in expected.items()}}


def vision_image():
    import base64
    import io
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (360, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 60, 280, 125), fill="#2060c0")
    draw.text((155, 85), "SAVE", fill="white", font_size=24)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
