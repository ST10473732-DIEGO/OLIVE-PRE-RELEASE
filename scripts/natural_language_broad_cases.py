"""Multi-domain release evaluation samples; never imported by OLIVE product code."""

from natural_language_extended_cases import CASES as BASE

FILE = {"entities": {"path": "C:/fixture/report.pdf"}}
WORKSPACE = {"workspace_id": "fixture", "entities": {"project": "OLIVE", "path": "C:/fixture/main.py"}}
DRAFT = {"pending_draft": {"type": "communication", "state": "prepared", "entities": {
    "application": "Relay", "recipient": "john@example.test", "message": "hello"}}}
CASES = list(BASE)

# Explicit examples intentionally vary vocabulary, domain and entity names.
for text, name in [
    ("Bring Calculator up", "Calculator"), ("Can you jump on Discord?", "Discord"),
    ("Start Discord for me", "Discord"), ("Launch Edge please", "Edge"),
    ("I'd like you to open Spotify", "Spotify"), ("Get File Explorer open", "File Explorer"),
    ("Could you bring VS Code up?", "VS Code"), ("Please launch Microsoft Store", "Microsoft Store"),
    ("Open Paint for me", "Paint"), ("Bring Obsidian up", "Obsidian"),
    ("Get Krita running", "Krita"), ("Launch Cedar Notes", "Cedar Notes"),
    ("Bring Juniper Canvas up", "Juniper Canvas"), ("Open Willow Archive", "Willow Archive"),
    ("Start Copper Journal", "Copper Journal"), ("Get Quartz Editor open", "Quartz Editor"),
    ("Please launch Ember Draw", "Ember Draw"), ("Open Larch Reader", "Larch Reader"),
    ("Start Birch Planner", "Birch Planner"), ("Bring Aspen Board up", "Aspen Board"),
]:
    CASES.append((text, ["application.launch"], {"application": name}, {}))

for text, entities in [
    ("Find report.pdf", {"query": "report.pdf"}),
    ("Find the PDF I downloaded yesterday", {"query": "*.pdf", "path": "Downloads"}),
    ("Can you find the file I got yesterday in Downloads?", {"query": "*", "path": "Downloads"}),
    ("Look for that project management PDF in my downloads", {"path": "Downloads", "extension": "pdf"}),
    ("Find my latest PDF", {"query": "*.pdf", "order": "latest"}),
    ("Locate notes.txt in Documents", {"query": "notes.txt", "path": "Documents"}),
    ("Find the spreadsheet I modified today in Documents", {"path": "Documents"}),
    ("Look for PDFs from this week in Downloads", {"query": "*.pdf", "path": "Downloads"}),
    ("Find the PDF created this morning in Documents", {"query": "*.pdf", "time_until": "12:00"}),
    ("Locate the newest invoice in Downloads", {"order": "latest", "path": "Downloads"}),
    ("Find the text file I modified yesterday in Documents", {"query": "*.txt", "path": "Documents"}),
    ("Look for slides.pdf in Downloads", {"query": "slides.pdf", "path": "Downloads"}),
]:
    CASES.append((text, ["filesystem.search"], entities, {}))

for text, intent, entities in [
    ("Skip this song", "media.next", {}), ("Go to the previous track", "media.previous", {}),
    ("Play some Drake", "media.play", {"query": "Drake"}),
    ("Put Starboy on", "media.play", {"query": "Starboy"}),
    ("I want to listen to Starboy", "media.play", {"query": "Starboy"}),
    ("Pause it", "media.pause", {}), ("Resume the music", "media.play", {}),
]:
    CASES.append((text, [intent], entities, {"media_application": "Player"}))

for text, intent in [
    ("Run the project", "code.run"), ("Check the existing tests", "code.test"),
    ("Why is this function failing?", "code.inspect"), ("Fix that error", "code.modify"),
    ("Write tests for this module", "code.modify"), ("Explain this source file", "code.inspect"),
    ("Repair the failing assertion", "code.modify"), ("Execute its test suite", "code.test"),
]:
    CASES.append((text, [intent], {}, WORKSPACE))

for text in [
    "Find out whether there's a better vision model", "Research current embedding models",
    "See what the latest SQLite documentation says", "Look up current Python release notes",
    "Investigate free local speech recognition options", "Research battery recycling evidence",
    "Find recent sources about small language models", "Check the latest documentation for this error",
]:
    CASES.append((text, ["research.start"], {}, WORKSPACE if "error" in text else {}))

for text, message in [
    ("Actually say hello everyone", "hello everyone"),
    ("Change it to I'll be late", "I'll be late"),
    ("No, make it see you tomorrow", "see you tomorrow"),
    ("I meant thanks for your help", "thanks for your help"),
    ("Replace that with good morning", "good morning"),
    ("Use this instead: meeting at noon", "meeting at noon"),
    ("Don't say hello, say welcome everyone", "welcome everyone"),
    ("Make the message hello everyone, how are you guys?", "hello everyone, how are you guys?"),
]:
    CASES.append((text, ["task.correct"], {"message": message}, DRAFT))
for text in ["Don't send it", "Never mind", "Cancel that", "Stop", "Cancel the message"]:
    CASES.append((text, ["task.cancel"], {}, DRAFT))
for text in ["Wait", "Leave it as a draft", "Hold the message for now"]:
    CASES.append((text, ["task.pause"], {}, DRAFT))

for text, intent in [
    ("Open that PDF", "filesystem.open"), ("Open the file", "filesystem.open"),
    ("Summarize this document", "knowledge.query"), ("What does it say?", "knowledge.query"),
    ("Attach it", "communication.attach"), ("Attach that file", "communication.attach"),
    ("Copy it to Documents", "filesystem.copy"), ("Move that PDF to Documents", "filesystem.move"),
]:
    CASES.append((text, [intent], {"path": "C:/fixture/report.pdf"}, FILE))

for text, intent, entities in [
    ("Open a new tab", "browser.interact", {"action": "new_tab"}),
    ("Search the web for Qwen", "browser.search", {"query": "Qwen"}),
    ("Take me to https://example.com", "browser.navigate", {"url": "https://example.com"}),
    ("Browse to https://example.org", "browser.navigate", {"url": "https://example.org"}),
    ("Look for SQLite using my browser", "browser.search", {"query": "SQLite"}),
    ("Make another browser tab", "browser.interact", {"action": "new_tab"}),
    ("Navigate to https://example.net", "browser.navigate", {"url": "https://example.net"}),
    ("Find information about Ollama in the browser", "browser.search", {"query": "Ollama"}),
    ("Open a fresh browser tab", "browser.interact", {"action": "new_tab"}),
    ("Take the browser to https://example.com/docs", "browser.navigate", {"url": "https://example.com/docs"}),
    ("Search online for PySide6", "browser.search", {"query": "PySide6"}),
    ("Show https://example.org/help in the browser", "browser.navigate", {"url": "https://example.org/help"}),
    ("Create a blank tab", "browser.interact", {"action": "new_tab"}),
    ("Do a browser search for local AI", "browser.search", {"query": "local AI"}),
]:
    CASES.append((text, [intent], entities, {"browser_application": "Chrome"}))

for text in [
    "Draft a message to john@example.test saying hello", "Prepare a note to john@example.test saying hello",
    "Write an unsent message to john@example.test saying hello", "Make a draft for john@example.test saying hello",
    "Compose a message to john@example.test saying hello", "Keep a message for john@example.test saying hello as a draft",
]:
    CASES.append((text, ["communication.compose"], {"recipient": "john@example.test", "message": "hello"}, {}))
for text in [
    "Send john@example.test a message saying hello", "Tell john@example.test hello",
    "Please send hello to john@example.test", "Message john@example.test saying hello",
    "Deliver hello to john@example.test", "Send a note saying hello to john@example.test",
]:
    CASES.append((text, ["communication.send"], {"recipient": "john@example.test", "message": "hello"}, {}))

for text, intents, entities in [
    ("Open Notepad then launch Calculator", ["application.launch", "application.launch"], {"application": "Calculator"}),
    ("Launch Chrome and go to https://example.com", ["application.launch", "application.navigate"], {"url": "https://example.com"}),
    ("Open my OLIVE project and run it", ["project.open", "code.run"], {"project": "OLIVE"}),
    ("Open my OLIVE project and check its tests", ["project.open", "code.test"], {"project": "OLIVE"}),
    ("Pause the music and open Calculator", ["media.pause", "application.launch"], {"application": "Calculator"}),
    ("Open Notepad then research current SQLite documentation", ["application.launch", "research.start"], {}),
    ("Find report.pdf in Downloads then open Calculator", ["filesystem.search", "application.launch"], {"application": "Calculator"}),
    ("Open display settings then launch Notepad", ["application.navigate", "application.launch"], {"application": "Notepad"}),
    ("Draft hello to john@example.test then pause the music", ["communication.compose", "media.pause"], {"message": "hello"}),
    ("Open Calculator then play Starboy", ["application.launch", "media.play"], {"query": "Starboy"}),
]:
    CASES.append((text, intents, entities, {"saved_project_names": ["OLIVE"]}))
