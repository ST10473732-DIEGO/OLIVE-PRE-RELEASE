from __future__ import annotations

from abc import ABC, abstractmethod
import csv
from dataclasses import dataclass
import io
from pathlib import Path
import re
import shutil
import sys
import subprocess


@dataclass(slots=True)
class OCRResult:
    text: str
    confidence: float | None = None


class OCRProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def recognize(self, image_path: Path) -> OCRResult: ...


class TesseractProvider(OCRProvider):
    def __init__(self, executable: str | None = None):
        self.executable = self.discover(executable)

    @staticmethod
    def discover(configured: str | None = None) -> str | None:
        candidates = [configured, shutil.which("tesseract")]
        for root in (Path("C:/Program Files"), Path("C:/Program Files (x86)")):
            candidates.append(str(root / "Tesseract-OCR" / "tesseract.exe"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        return None

    @property
    def name(self) -> str:
        return "Tesseract"

    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).is_file())

    def capabilities(self) -> dict:
        return {"confidence": True, "page_images": True, "local": True}

    def version(self) -> str | None:
        if not self.available(): return None
        result = self._run([str(self.executable), "--version"], timeout=10)
        return result.stdout.splitlines()[0].strip() if result.returncode == 0 and result.stdout else None

    def recognize(self, image_path: Path) -> OCRResult:
        if not self.available():
            raise RuntimeError("Local OCR is unavailable. Install local Tesseract OCR or configure its executable.")
        result = self._run([str(self.executable), str(image_path), "stdout", "tsv"], timeout=120)
        if result.returncode:
            raise RuntimeError(f"Tesseract failed with exit code {result.returncode}")
        text, confidence = parse_tesseract_tsv(result.stdout)
        return OCRResult(clean_ocr_text(text), confidence)

    @staticmethod
    def _run(command: list[str], timeout: int):
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class OCRService:
    def __init__(self, executable: str | None = None, provider: OCRProvider | None = None):
        self.provider = provider or TesseractProvider(executable)

    @property
    def executable(self) -> str | None:
        return getattr(self.provider, "executable", None)

    @executable.setter
    def executable(self, value: str | None) -> None:
        if hasattr(self.provider, "executable"):
            self.provider.executable = value

    @property
    def available(self) -> bool:
        return self.provider.available()

    @property
    def installation_hint(self) -> str:
        return "Install Tesseract OCR for Windows or choose tesseract.exe in Settings." if sys.platform == "win32" else "Install Tesseract OCR or choose its executable in Settings."

    def diagnostics(self) -> dict:
        version = self.provider.version() if hasattr(self.provider, "version") else None
        return {"provider": self.provider.name, "executable": self.executable or "Not found",
                "version": version or "Unavailable",
                "confidence_available": bool(self.provider.capabilities().get("confidence"))}

    @staticmethod
    def validate_executable(path: str) -> str:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file() or resolved.name.lower() != "tesseract.exe":
            raise ValueError("Select a valid tesseract.exe file")
        result = TesseractProvider._run([str(resolved), "--version"], 10)
        if result.returncode != 0 or "tesseract" not in result.stdout.lower():
            raise ValueError("The selected executable is not a working Tesseract installation")
        return str(resolved)

    def recognize(self, image_path: Path) -> OCRResult:
        return self.provider.recognize(image_path)


def parse_tesseract_tsv(value: str) -> tuple[str, float | None]:
    rows = csv.DictReader(io.StringIO(value), delimiter="\t")
    lines: dict[tuple[str, str, str, str], list[str]] = {}
    confidences = []
    for row in rows:
        word = (row.get("text") or "").strip()
        if not word: continue
        key = tuple(row.get(field, "") for field in ("block_num", "par_num", "line_num", "page_num"))
        lines.setdefault(key, []).append(word)
        try:
            confidence = float(row.get("conf", "-1"))
            if confidence >= 0: confidences.append(confidence)
        except ValueError:
            continue
    text = "\n".join(" ".join(words) for words in lines.values())
    return text, (round(sum(confidences) / len(confidences), 2) if confidences else None)


def clean_ocr_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.replace("\r", "").split("\n")]
    output, blank = [], False
    for line in lines:
        if line:
            output.append(line); blank = False
        elif output and not blank:
            output.append(""); blank = True
    return "\n".join(output).strip()


def is_ocr_candidate(text: str, image_count: int, minimum_useful_characters: int = 40) -> bool:
    return image_count > 0 and sum(character.isalnum() for character in text) < minimum_useful_characters
