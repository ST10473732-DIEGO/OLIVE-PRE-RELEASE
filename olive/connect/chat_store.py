"""Durable remote-Chat receipts and a private, content-addressed attachment staging area.

Receipts make ``start`` idempotent and let a phone recover a request's outcome
after a lost acknowledgement, a reconnect or a desktop restart. They hold the
answer text, structured sources and artifact descriptors (never prompts,
attachment bytes, model tags or filesystem paths).

Staging is OLIVE-owned: ``<profile>/connect/chat-staging/<peer>/<sha256>.<ext>``.
Peer-supplied names are display metadata only and never become paths. Partial
uploads are ``.part`` files that never become visible to a model; a file is
published only after its SHA-256 and content type are verified.
"""
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from .chat_protocol import MAX_BYTES, TERMINAL
from .contracts import ConnectError, identifier

EXTENSIONS = {'image/png': '.png', 'image/jpeg': '.jpg', 'application/pdf': '.pdf', 'text/plain': '.txt',
              'text/markdown': '.md', 'text/x-source': '.txt',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'}
PEER_BYTES = 512 * 1024 * 1024
PEER_PARTIALS = 8
PARTIAL_SECONDS = 24 * 3600
STAGED_SECONDS = 30 * 24 * 3600
RECEIPTS_PER_PEER = 2000
RECEIPT_SECONDS = 30 * 24 * 3600
_HEX64 = re.compile('[0-9a-f]{64}')


class ChatStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS remote_chat_v1 (
                peer TEXT NOT NULL, job TEXT NOT NULL, fingerprint TEXT NOT NULL, conversation TEXT NOT NULL,
                mode TEXT NOT NULL, state TEXT NOT NULL, error TEXT, text TEXT NOT NULL DEFAULT '',
                sources TEXT NOT NULL DEFAULT '[]', artifacts TEXT NOT NULL DEFAULT '[]',
                attribution TEXT NOT NULL DEFAULT '{}', created INTEGER NOT NULL, updated INTEGER NOT NULL,
                PRIMARY KEY(peer, job))''')
            db.execute('''CREATE TABLE IF NOT EXISTS remote_chat_conversations_v1 (
                peer TEXT NOT NULL, conversation TEXT NOT NULL, state TEXT NOT NULL, used INTEGER NOT NULL,
                PRIMARY KEY(peer, conversation))''')
            # Work that was live when OLIVE stopped cannot be resumed or safely
            # replayed. Its outcome is unknown; the phone never regenerates it.
            db.execute("UPDATE remote_chat_v1 SET state='outcome_unknown', error='request_indeterminate' "
                       "WHERE state NOT IN ('completed','cancelled','failed','outcome_unknown')")

    @staticmethod
    def get(db, peer, job):
        row = db.execute('SELECT fingerprint,conversation,mode,state,error,text,sources,artifacts,attribution '
                         'FROM remote_chat_v1 WHERE peer=? AND job=?', (peer, job)).fetchone()
        if not row:
            return None
        return dict(fingerprint=row[0], conversation=row[1], mode=row[2], state=row[3], error=row[4], text=row[5],
                    sources=json.loads(row[6]), artifacts=json.loads(row[7]), attribution=json.loads(row[8]))

    @staticmethod
    def claim(db, peer, job, fingerprint, conversation, mode, state, now):
        count = db.execute('SELECT count(*) FROM remote_chat_v1 WHERE peer=?', (peer,)).fetchone()[0]
        if count >= RECEIPTS_PER_PEER:
            db.execute('DELETE FROM remote_chat_v1 WHERE peer=? AND updated<? AND state IN '
                       "('completed','cancelled','failed','outcome_unknown')", (peer, now - RECEIPT_SECONDS))
            if db.execute('SELECT count(*) FROM remote_chat_v1 WHERE peer=?', (peer,)).fetchone()[0] >= RECEIPTS_PER_PEER:
                raise ConnectError('ledger_full')
        db.execute('INSERT INTO remote_chat_v1(peer,job,fingerprint,conversation,mode,state,created,updated) '
                   'VALUES(?,?,?,?,?,?,?,?)', (peer, job, fingerprint, conversation, mode, state, now, now))

    @staticmethod
    def update(db, peer, job, *, state, error=None, text='', sources=(), artifacts=(), attribution=None, now):
        db.execute('UPDATE remote_chat_v1 SET state=?,error=?,text=?,sources=?,artifacts=?,attribution=?,updated=? '
                   'WHERE peer=? AND job=?', (state, error, text, json.dumps(list(sources)), json.dumps(list(artifacts)),
                                              json.dumps(attribution or {}), now, peer, job))

    @staticmethod
    def artifact_owned(db, peer, artifact_id):
        """An artifact is readable only by the peer whose completed job produced it."""
        for (artifacts,) in db.execute("SELECT artifacts FROM remote_chat_v1 WHERE peer=? AND state='completed' "
                                       "AND artifacts LIKE ?", (peer, '%' + artifact_id + '%')):
            if any(item.get('artifact_id') == artifact_id for item in json.loads(artifacts)):
                return True
        return False

    @staticmethod
    def conversation(db, peer, conversation):
        row = db.execute('SELECT state FROM remote_chat_conversations_v1 WHERE peer=? AND conversation=?',
                         (peer, conversation)).fetchone()
        return json.loads(row[0]) if row else {}

    @staticmethod
    def save_conversation(db, peer, conversation, state, now):
        db.execute('INSERT OR REPLACE INTO remote_chat_conversations_v1 VALUES(?,?,?,?)',
                   (peer, conversation, json.dumps(state), now))

    @staticmethod
    def stale_conversations(db, now):
        return db.execute('SELECT peer,conversation,state FROM remote_chat_conversations_v1 WHERE used<?',
                          (now - STAGED_SECONDS,)).fetchall()

    @staticmethod
    def forget_conversation(db, peer, conversation):
        db.execute('DELETE FROM remote_chat_conversations_v1 WHERE peer=? AND conversation=?', (peer, conversation))

    @staticmethod
    def forget_peer(db, peer):
        rows = db.execute('SELECT conversation,state FROM remote_chat_conversations_v1 WHERE peer=?', (peer,)).fetchall()
        db.execute('DELETE FROM remote_chat_conversations_v1 WHERE peer=?', (peer,))
        return rows


def _sniff(path, mime):
    """Verify the actual content, not the declared type or extension."""
    with open(path, 'rb') as stream:
        head = stream.read(8)
    if mime == 'image/png' or mime == 'image/jpeg':
        magic = b'\x89PNG\r\n\x1a\n' if mime == 'image/png' else b'\xff\xd8\xff'
        if not head.startswith(magic):
            return False
        try:
            from PIL import Image
            with Image.open(path) as image:
                if image.format != ('PNG' if mime == 'image/png' else 'JPEG') or image.width * image.height > 24_000_000:
                    return False
                image.verify()
        except Exception:
            return False
        return True
    if mime == 'application/pdf':
        return head.startswith(b'%PDF-')
    if mime.endswith('wordprocessingml.document'):
        return head.startswith(b'PK\x03\x04')
    # Text: strict UTF-8, no NUL, read in bounded pieces.
    import codecs
    decode = codecs.getincrementaldecoder('utf-8')('strict')
    try:
        with open(path, 'rb') as stream:
            while True:
                block = stream.read(65536)
                if not block:
                    decode.decode(b'', final=True)
                    return True
                if b'\0' in block:
                    return False
                decode.decode(block)
    except UnicodeDecodeError:
        return False


class AttachmentStaging:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root)
        self.clock = clock

    def _dir(self, peer):
        identifier(peer)
        path = self.root / peer
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def _paths(self, peer, attachment_id, mime):
        if not _HEX64.fullmatch(attachment_id) or mime not in EXTENSIONS:
            raise ConnectError('invalid_request')
        base = self._dir(peer)
        return base / (attachment_id + '.part'), base / (attachment_id + EXTENSIONS[mime]), base / (attachment_id + '.json')

    def _meta(self, peer, attachment_id):
        base = self._dir(peer)
        try:
            meta = json.loads((base / (attachment_id + '.json')).read_text('utf-8'))
        except (OSError, ValueError):
            return None
        if type(meta) is not dict or meta.get('mime') not in EXTENSIONS:
            return None
        return meta

    def present(self, peer, ref):
        """Path of a verified staged file matching this descriptor, or None."""
        meta = self._meta(peer, ref['attachment_id'])
        if not meta or meta.get('mime') != ref['mime'] or meta.get('size') != ref['size'] or meta.get('kind') != ref['kind']:
            return None
        final = self._paths(peer, ref['attachment_id'], ref['mime'])[1]
        if not final.is_file() or final.stat().st_size != ref['size']:
            return None
        os.utime(final)  # Last use: staged inputs referenced by recent requests are kept.
        return final

    def _usage(self, peer):
        base = self._dir(peer)
        total, partials = 0, []
        for entry in base.iterdir():
            if entry.suffix == '.json':
                continue
            try:
                total += entry.stat().st_size
            except OSError:
                continue
            if entry.suffix == '.part':
                partials.append(entry)
        return total, partials

    def offer(self, peer, ref):
        if self.present(peer, ref):
            return 'present', ref['size']
        partial, final, meta_path = self._paths(peer, ref['attachment_id'], ref['mime'])
        meta = self._meta(peer, ref['attachment_id'])
        if meta and (meta.get('mime') != ref['mime'] or meta.get('size') != ref['size'] or meta.get('kind') != ref['kind']):
            # Same content address, different claims: the old partial is discarded.
            partial.unlink(missing_ok=True)
            meta = None
        if not partial.exists():
            self.collect(peer)
            total, partials = self._usage(peer)
            if len(partials) >= PEER_PARTIALS or total + ref['size'] > PEER_BYTES:
                raise ConnectError('storage_full')
            if shutil.disk_usage(self.root).free < ref['size'] + 256 * 1024 * 1024:
                raise ConnectError('storage_full')
            meta_path.write_text(json.dumps(dict(kind=ref['kind'], mime=ref['mime'], size=ref['size'])), 'utf-8')
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        return 'partial', partial.stat().st_size

    def chunk(self, peer, attachment_id, offset, data):
        meta = self._meta(peer, attachment_id)
        if not meta:
            raise ConnectError('attachment_missing')
        partial, final, meta_path = self._paths(peer, attachment_id, meta['mime'])
        if final.is_file() and final.stat().st_size == meta['size']:
            return 'present', meta['size']
        if not partial.exists():
            raise ConnectError('attachment_missing')
        received = partial.stat().st_size
        if offset != received:
            # A duplicate or out-of-order chunk: report the truth so the sender resumes there.
            return 'partial', received
        if received + len(data) > meta['size']:
            partial.unlink(missing_ok=True)
            raise ConnectError('attachment_corrupt')
        with open(partial, 'ab') as stream:
            stream.write(data)
            stream.flush()
            received = stream.tell()
        if received < meta['size']:
            return 'partial', received
        # Complete: verify the stored bytes, then publish exclusively.
        hasher = hashlib.sha256()
        with open(partial, 'rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                hasher.update(block)
        if hasher.hexdigest() != attachment_id:
            partial.unlink(missing_ok=True)
            raise ConnectError('attachment_corrupt')
        if not _sniff(partial, meta['mime']):
            partial.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            raise ConnectError('unsupported_attachment')
        with open(partial, 'rb+') as stream:
            os.fsync(stream.fileno())
        os.replace(partial, final)
        return 'present', meta['size']

    def collect(self, peer=None):
        """Remove abandoned partial uploads and long-unused staged inputs."""
        now = self.clock()
        peers = [peer] if peer else [p.name for p in self.root.iterdir() if p.is_dir()] if self.root.exists() else []
        removed = 0
        for name in peers:
            try:
                base = self._dir(name)
            except ConnectError:
                continue
            for entry in list(base.iterdir()):
                try:
                    age = now - entry.stat().st_mtime
                except OSError:
                    continue
                limit = PARTIAL_SECONDS if entry.suffix == '.part' else STAGED_SECONDS
                if entry.suffix != '.json' and age >= limit:
                    entry.unlink(missing_ok=True)
                    removed += 1
            for meta in list(base.glob('*.json')):
                if not any(p.suffix != '.json' for p in base.glob(meta.stem + '.*')):
                    meta.unlink(missing_ok=True)
        return removed

    def forget(self, peer):
        """Revocation/removal: drop everything staged for a peer."""
        try:
            shutil.rmtree(self._dir(peer))
        except OSError:
            pass
