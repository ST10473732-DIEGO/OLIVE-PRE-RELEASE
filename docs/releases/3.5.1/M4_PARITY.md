# M4 native Mail action parity

All routes reach one Python controller and existing permission/confirmation services.
The original 125 M2 mappings in PARITY.md remain unchanged. Evidence classifications
and actual UI versus protocol demonstrations are in M4_COMPLETION.md.

| Action | Electron / language access | Permission | State / evidence |
| --- | --- | --- | --- |
| `mail.folders` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.search` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.get` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.thread` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.create_folder` | Mail contextual UI; shared registered capability | `mail.modify` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.discard` | Mail contextual UI; shared registered capability | `mail.modify` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.inline_images` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.save_draft` | Mail contextual UI; shared registered capability | `mail.read`, `mail.draft` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.update` | Mail contextual UI; shared registered capability | `mail.modify` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.reply` | Mail contextual UI; shared registered capability | `mail.read`, `mail.draft` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.import_commit` | Mail contextual UI; shared registered capability | `mail.import` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.import_cancel` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.prepare` | Mail contextual UI; shared registered capability | `mail.read`, `mail.draft` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.send` | Mail contextual UI; shared registered capability | `communication.send`, `mail.send` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.cancel` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.outbox` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.sent_copy` | Mail contextual UI; shared registered capability | `mail.read`, `mail.remote_modify`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.retry_rejected` | Mail contextual UI; shared registered capability | `mail.read`, `mail.draft` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.connections` | Settings Connections; direct application consent only | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.sync` | Mail contextual UI; shared registered capability | `mail.read`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.cancel_sync` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.fetch_body` | Mail contextual UI; shared registered capability | `mail.read`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.remote_action` | Mail contextual UI; shared registered capability | `mail.read`, `mail.remote_modify`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.server_search` | Mail contextual UI; shared registered capability | `mail.read`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.folder_action` | Mail contextual UI; shared registered capability | `mail.read`, `mail.remote_modify`, `mail.connect` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.cache_remove` | Mail contextual UI; shared registered capability | `mail.connections`, `mail.modify` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.proposal_prepare` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.create_event` | Mail contextual UI; shared registered capability | `mail.read`, `calendar.write` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.create_task` | Mail contextual UI; shared registered capability | `mail.read`, `tasks.write` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.proposal_cancel` | Mail contextual UI; shared registered capability | `mail.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.from_event` | Mail contextual UI; shared registered capability | `mail.draft`, `calendar.read`, `contacts.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.add_knowledge` | Mail contextual UI; shared registered capability | `mail.read`, `knowledge.write` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.connection_save` | Settings Connections; direct application consent only; native main-process file/configuration route | `mail.connections` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.connection_state` | Settings Connections; direct application consent only; native main-process file/configuration route | `mail.connections` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.connection_test` | Settings Connections; direct application consent only; native main-process file/configuration route | `mail.connections` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.credential_store` | Dedicated masked control; never registered as a model tool | `mail.connections`, `mail.credentials` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.import_preview` | Mail contextual UI; shared registered capability; native main-process file/configuration route | `mail.draft`, `filesystem.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.export` | Mail contextual UI; shared registered capability; native main-process file/configuration route | `mail.read`, `mail.export`, `filesystem.write` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.attach` | Mail contextual UI; shared registered capability; native main-process file/configuration route | `mail.draft`, `filesystem.read` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |
| `mail.save_attachment` | Mail contextual UI; shared registered capability; native main-process file/configuration route | `mail.read`, `mail.export`, `filesystem.write` | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |

Local and remote outcomes are distinct. Send/remote changes retain uncertainty;
there is no automatic send replay. Entry-point existence is not claimed as a
live pass for every action. See MAIL_TRANSPORTS.md for supported protocol limits.
