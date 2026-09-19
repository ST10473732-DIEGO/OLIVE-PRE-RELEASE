from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import sqlite3
from contextlib import closing

from ..config import APP_VERSION

BACKUP_FORMAT_VERSION = 1


class BackupError(ValueError):
    pass


class BackupService:
    COMPONENTS = {
        "chats": "chats.json", "settings": "settings.json", "model_defaults": "model_defaults.json",
        "model_aliases": "model_aliases.json", "memories": "memories.json",
        "rag": "rag.sqlite3", "indexing_jobs": "indexing_jobs.json",
        "projects": "projects.json", "agent_tasks": "agent_tasks.json", "permissions": "permissions.json",
        "knowledge_sources": "knowledge_sources.json", "training_examples": "training_examples.json",
        "workspaces": "workspaces.json", "terminal_sessions": "terminal_sessions.json",
        "research_sessions": "research_sessions.json", "research_reports": "research_reports.json",
        "web_knowledge": "web_knowledge.json", "web_subscriptions": "web_subscriptions.json",
        "personal": "personal.sqlite3",
        "mail": "mail.sqlite3",
    }

    def __init__(self, data_dir: Path, backups_dir: Path | None = None):
        self.data_dir = data_dir
        self.backups_dir = backups_dir or data_dir / "backups"

    def create(self, destination: Path | None = None, components: set[str] | None = None) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        selected = components or set(self.COMPONENTS)
        unknown = selected - self.COMPONENTS.keys()
        if unknown: raise BackupError(f"Unknown backup components: {sorted(unknown)}")
        destination = destination or self.backups_dir / f"olive-{datetime.now():%Y%m%d-%H%M%S-%f}.zip"
        destination.parent.mkdir(parents=True, exist_ok=True)
        included, schemas = [], {}
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for component in sorted(selected):
                source = self.data_dir / self.COMPONENTS[component]
                if not source.is_file(): continue
                if component in {'rag','personal','mail'}:
                    # SQLite's backup API includes committed WAL transactions and
                    # yields a consistent snapshot while indexing connections live.
                    with tempfile.TemporaryDirectory(prefix='olive-backup-') as temporary:
                        snapshot = Path(temporary) / source.name
                        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as reader:
                            with closing(sqlite3.connect(snapshot)) as writer:
                                reader.backup(writer)
                        archive.write(snapshot, f"data/{source.name}")
                else:
                    archive.write(source, f"data/{source.name}")
                included.append(component)
                schemas[component] = self._schema_version(source, component)
            manifest = {"backup_format_version": BACKUP_FORMAT_VERSION, "product": "OLIVE", "olive_version": APP_VERSION,
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "included_components": included, "schema_versions": schemas}
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        return destination

    def validate(self, archive_path: Path) -> dict:
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                names = set(archive.namelist())
                if len(names)!=len(archive.namelist()):raise BackupError('Backup contains duplicate entries')
                allowed={'manifest.json',*[f'data/{name}' for name in self.COMPONENTS.values()]}
                if names-allowed:raise BackupError('Backup contains unexpected paths or components')
                if sum(info.file_size for info in archive.infolist())>1_000_000_000 or any(info.file_size>512_000_000 for info in archive.infolist()):raise BackupError('Backup exceeds the supported restore size')
                if 'manifest.json' in names and archive.getinfo('manifest.json').file_size>1_000_000:raise BackupError('Backup manifest exceeds its size limit')
                if "manifest.json" not in names: raise BackupError("Backup manifest is missing")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("backup_format_version") != BACKUP_FORMAT_VERSION:
                    raise BackupError("Unsupported backup format version")
                if manifest.get("product") not in {None,"OLIVE","DMDO"}: raise BackupError("Unsupported backup product identity")
                included = manifest.get("included_components")
                if not isinstance(included, list): raise BackupError("Invalid component list")
                for component in included:
                    if component not in self.COMPONENTS: raise BackupError("Backup contains unknown component")
                    if f"data/{self.COMPONENTS[component]}" not in names:
                        raise BackupError(f"Backup component is missing: {component}")
                return manifest
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
            raise BackupError(f"Invalid OLIVE backup: {exc}") from exc

    def restore(self, archive_path: Path, *, confirmed: bool = False) -> Path:
        if not confirmed: raise PermissionError("Restore requires explicit confirmation")
        manifest = self.validate(archive_path)
        safety = self.create()
        replaced: list[tuple[Path, Path | None]] = []
        staging = Path(tempfile.mkdtemp(prefix="olive-restore-"))
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for component in manifest["included_components"]:
                    filename = self.COMPONENTS[component]
                    staged = staging / filename
                    staged.write_bytes(archive.read(f"data/{filename}"))
                    self._validate_component(staged, component)
                    if component=='personal':
                        from ..personal.store import PersonalStore,timestamp
                        store=PersonalStore(staged);cutoff=timestamp()
                        with store.transaction() as db:
                            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('restore_cutoff',?)",(cutoff,))
                            db.execute("UPDATE deliveries SET state='restored',updated_at=? WHERE state IN ('pending','snoozed') AND due_at<=?",(cutoff,cutoff))
                    if component=='mail':
                        from ..mail.store import MailStore
                        MailStore(staged).recover(restored=True)
                self._validate_personal_external_links(staging)
                self._validate_mail_external_links(staging)
                for component in manifest["included_components"]:
                    filename = self.COMPONENTS[component]; target = self.data_dir / filename
                    rollback = staging / f"rollback-{filename}"
                    if target.exists(): shutil.copy2(target, rollback)
                    staged = staging / filename; target.parent.mkdir(parents=True, exist_ok=True)
                    temp_target = target.with_suffix(target.suffix + ".restore")
                    shutil.copy2(staged, temp_target); temp_target.replace(target)
                    replaced.append((target, rollback if rollback.exists() else None))
        except Exception:
            for target, rollback in reversed(replaced):
                if rollback and rollback.exists(): shutil.copy2(rollback, target)
                elif target.exists(): target.unlink()
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return safety

    def _validate_personal_external_links(self, staging: Path) -> None:
        """Check the effective restored stores before replacing any live file."""
        def effective(name):
            staged=staging/name
            return staged if staged.exists() else self.data_dir/name
        personal=effective('personal.sqlite3')
        if not personal.exists():return
        def identities(filename,key):
            path=effective(filename)
            if not path.exists():return set()
            payload=json.loads(path.read_text(encoding='utf-8'))
            return {record['id'] for record in payload.get(key,[])}
        projects=identities('projects.json','projects');attempts=identities('agent_tasks.json','tasks')
        with closing(sqlite3.connect(personal.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for (encoded,) in db.execute('SELECT body FROM records WHERE deleted=0'):
                body=json.loads(encoded)
                links=body.get('project_ids',[body.get('project_id','')])
                if any(identity and identity not in projects for identity in links):
                    raise BackupError('Restore would leave missing project references. Include the linked Projects component.')
                if body.get('agent_task_id') and body['agent_task_id'] not in attempts:
                    raise BackupError('Restore would leave a missing Agent attempt reference. Include the linked Agent tasks component.')

    def _validate_mail_external_links(self, staging: Path) -> None:
        def effective(name):
            return staging/name if (staging/name).exists() else self.data_dir/name
        mail=effective('mail.sqlite3')
        if not mail.exists():return
        def identities(name,key):
            p=effective(name)
            return {r['id'] for r in json.loads(p.read_text(encoding='utf-8')).get(key,[])} if p.exists() else set()
        projects=identities('projects.json','projects');chats=identities('chats.json','chats')
        personal=effective('personal.sqlite3');native=set()
        if personal.exists():
            with closing(sqlite3.connect(personal.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                native={r[0] for r in db.execute('SELECT id FROM records')}
        with closing(sqlite3.connect(mail.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for (encoded,) in db.execute('SELECT body FROM records'):
                body=json.loads(encoded)
                if body.get('project_id') and body['project_id'] not in projects:raise BackupError('Mail references missing Projects; include the linked component')
                if body.get('type')=='native_proposal' and body.get('target_id') and body['target_id'] not in native:raise BackupError('Mail references missing Personal Core records; include the linked component')
                if body.get('type')=='knowledge_source' and body.get('chat_id') not in chats:raise BackupError('Mail Knowledge references missing Chats; include the linked component')

    def export_chats(self, destination: Path, chats: list[dict]) -> Path:
        destination.write_text(json.dumps({"schema_version": 2, "chats": chats}, indent=2), encoding="utf-8")
        return destination

    def export_memories(self, destination: Path, memories: list[dict]) -> Path:
        destination.write_text(json.dumps({"schema_version": 1, "memories": memories}, indent=2), encoding="utf-8")
        return destination

    @staticmethod
    def _schema_version(path: Path, component: str) -> int:
        if path.suffix == ".json":
            try: return int(json.loads(path.read_text(encoding="utf-8")).get("schema_version", 1))
            except (OSError, json.JSONDecodeError): return 0
        if component in {'personal','mail'}:
            with closing(sqlite3.connect(path)) as db:return db.execute('PRAGMA user_version').fetchone()[0]
        return 2 if component == "rag" else 1

    @staticmethod
    def _validate_component(path: Path, component: str) -> None:
        if component == 'mail':
            from ..mail.store import MailStore
            MailStore.validate_database(path)
            return
        if component == 'personal':
            from ..personal.store import PersonalStore
            PersonalStore.validate_database(path)
            return
        if path.suffix == ".json": json.loads(path.read_text(encoding="utf-8"))
        elif component == "rag":
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(path)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("RAG database integrity check failed")
