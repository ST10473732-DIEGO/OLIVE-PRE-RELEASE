from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .identity import APP_NAME, APP_VERSION, resolve_profile

DATA_DIR = resolve_profile()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENTS_DIR = DATA_DIR / "attachments"
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

CHATS_FILE = DATA_DIR / "chats.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
MODEL_DEFAULTS_FILE = DATA_DIR / "model_defaults.json"
MODEL_ALIASES_FILE = DATA_DIR / "model_aliases.json"
RAG_DB_FILE = DATA_DIR / "rag.sqlite3"
MEMORIES_FILE = DATA_DIR / "memories.json"
LOGS_DIR = DATA_DIR / "logs"
INDEXING_JOBS_FILE = DATA_DIR / "indexing_jobs.json"
BACKUPS_DIR = DATA_DIR / "backups"
PROJECTS_FILE = DATA_DIR / "projects.json"
AGENT_TASKS_FILE = DATA_DIR / "agent_tasks.json"
PERMISSIONS_FILE = DATA_DIR / "permissions.json"
AGENT_AUDIT_FILE = DATA_DIR / "agent_audit.jsonl"
KNOWLEDGE_SOURCES_FILE = DATA_DIR / "knowledge_sources.json"
TRAINING_EXAMPLES_FILE = DATA_DIR / "training_examples.json"
WORKSPACES_FILE = DATA_DIR / "workspaces.json"
TERMINAL_SESSIONS_FILE = DATA_DIR / "terminal_sessions.json"
CODE_INDEXES_DIR = DATA_DIR / "code_indexes"
TASK_CHECKPOINTS_DIR = DATA_DIR / "task_checkpoints"

LEGACY_DATA_DIR = Path.home() / ".aether"

OLLAMA_HOST = os.getenv("OLIVE_OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("OLIVE_EMBEDDING_MODEL", "nomic-embed-text")

DEFAULT_SYSTEM_PROMPT = """You are OLIVE, a private local AI assistant.

Priorities:
- Be accurate, direct, practical, and clear.
- Distinguish facts, estimates, assumptions, and opinions.
- Do not invent citations, file contents, tool results, or capabilities.
- When document context is provided, use it carefully and reference the supplied source labels when useful.
- If the answer depends on missing information, say what is missing rather than guessing.
- Prefer concise answers unless the user asks for detail.
- For technical work, give runnable, maintainable solutions and explain important trade-offs.
"""

PROMPT_PRESETS = {
    "OLIVE Default": DEFAULT_SYSTEM_PROMPT,
    "Direct Analyst": """You are OLIVE, a direct analytical assistant. Prioritise correctness, evidence, explicit assumptions, and actionable conclusions. Do not pad answers with unnecessary commentary.""",
    "Technical": """You are OLIVE, a senior technical collaborator. Give precise, implementation-ready guidance, call out failure modes, preserve compatibility, and prefer maintainable solutions over quick hacks.""",
    "Creative": """You are OLIVE, a creative collaborator. Generate original ideas with strong structure, vivid detail, and stylistic consistency while following the user's requested format and tone.""",
    "Minimal": "You are OLIVE, a helpful AI assistant. Be concise and accurate.",
}

# Used only as a fallback if Ollama does not report capabilities.
VISION_NAME_HINTS = (
    "vision",
    "llava",
    "bakllava",
    "moondream",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "gemma3",
    "cogvlm",
    "phi3-vision",
    "llama3.2-vision",
)

EMBEDDING_NAME_HINTS = (
    "embed",
    "embedding",
    "nomic-embed",
    "mxbai-embed",
    "bge-",
    "snowflake-arctic-embed",
)


@dataclass(slots=True)
class GenerationDefaults:
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 4096
    repeat_penalty: float = 1.08
    history_messages: int = 36
    rag_top_k: int = 6


DEFAULT_GENERATION = GenerationDefaults()
