"""Seed synthetic local mail into an empty temporary profile for visual capture.

Usage: seed_visual_mail.py <profile> <eml>...   (evidence fixtures only)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    profile = Path(sys.argv[1]).resolve()
    if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("Use a temporary profile for synthetic fixtures")
    os.environ["OLIVE_DATA_DIR"] = str(profile)
    from olive.mail.local import LocalMail
    from olive.mail.store import MailStore

    store = MailStore(profile / "mail.sqlite3")
    store.recover()
    local = LocalMail(store)
    for eml in sys.argv[2:]:
        raw = Path(eml).read_bytes()
        local.ingest(raw, source="fixture:" + Path(eml).name)
    store.close() if hasattr(store, "close") else None


if __name__ == "__main__":
    main()
