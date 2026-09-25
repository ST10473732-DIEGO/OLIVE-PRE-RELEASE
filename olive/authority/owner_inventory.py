"""Complete Owner Mode classification of registered local typed controllers.

This table is policy documentation that tests keep in lockstep with the tool
registry. It never grants authority on its own: `OwnerPolicy` still derives a
per-task grant from the literal local request and binds exact resources. Deny,
Stop, expiry, remote isolation and OS authentication remain authoritative.
"""

OWNER_AUTO_FOR_EXPLICIT_TASK = 'OWNER_AUTO_FOR_EXPLICIT_TASK'
OWNER_AUTO_READ_ONLY = 'OWNER_AUTO_READ_ONLY'
HIGH_IMPACT_EXPLICIT_PATH = 'HIGH_IMPACT_EXPLICIT_PATH'
OS_AUTH_REQUIRED = 'OS_AUTH_REQUIRED'
REMOTE_RULES_ONLY = 'REMOTE_RULES_ONLY'
UNSUPPORTED = 'UNSUPPORTED'
NOT_SAFE_FOR_OWNER_AUTO = 'NOT_SAFE_FOR_OWNER_AUTO'
DEPRECATED = 'DEPRECATED'
CLASSES = (OWNER_AUTO_FOR_EXPLICIT_TASK, OWNER_AUTO_READ_ONLY, HIGH_IMPACT_EXPLICIT_PATH, OS_AUTH_REQUIRED,
           REMOTE_RULES_ONLY, UNSUPPORTED, NOT_SAFE_FOR_OWNER_AUTO, DEPRECATED)

A, R, H, N, D = (OWNER_AUTO_FOR_EXPLICIT_TASK, OWNER_AUTO_READ_ONLY, HIGH_IMPACT_EXPLICIT_PATH,
                 NOT_SAFE_FOR_OWNER_AUTO, DEPRECATED)


def _rows(family, classification, binding, *names):
    return {name: (classification, family, binding) for name in names}


INVENTORY = {}
# Filesystem: exact literal paths; owned, no symlink traversal, no credentials.
INVENTORY.update(_rows('filesystem', R, 'literal path or its descendants',
                       'filesystem.stat', 'filesystem.read_text', 'filesystem.list', 'filesystem.search'))
INVENTORY.update(_rows('filesystem', A, 'literal path; collision refused; one reservation per tool',
                       'filesystem.create_directory', 'filesystem.write_text', 'filesystem.copy',
                       'filesystem.move', 'filesystem.trash'))
INVENTORY.update(_rows('filesystem', H, 'permanent deletion is never inferred from delete/trash',
                       'filesystem.delete'))
# Code/workspace: one selected approved workspace plus an explicit software target.
INVENTORY.update(_rows('code', R, 'selected approved workspace',
                       'code.read_file', 'code.read_range', 'code.search_text', 'code.search_symbol',
                       'code.list_symbols', 'code.find_references'))
INVENTORY.update(_rows('code', A, 'selected approved workspace; bounded edit budget',
                       'code.replace_exact', 'code.replace_range', 'code.create_file'))
# Git: typed controller only; no command strings.
INVENTORY.update(_rows('git', R, 'selected approved repository root',
                       'git.status', 'git.diff', 'git.log', 'git.branch_list'))
INVENTORY.update(_rows('git', A, 'selected approved repository; literal branch/message; each once',
                       'git.add', 'git.commit', 'git.create_branch', 'git.checkout'))
# Studio.
INVENTORY.update(_rows('studio', R, 'selected approved workspace',
                       'studio.open', 'studio.tree', 'studio.search', 'studio.compare', 'studio.designer_read',
                       'studio.language_service'))
INVENTORY.update(_rows('studio', A, 'selected approved workspace; detected commands only',
                       'studio.run', 'studio.build', 'studio.test', 'studio.debug', 'studio.launch',
                       'workspace.run_validation', 'studio.save', 'studio.designer_save', 'studio.create',
                       'studio.new_project', 'studio.scaffold', 'workspace.create_template'))
INVENTORY.update(_rows('studio', H, 'checkpoint history rewrite requires an explicit request',
                       'studio.rollback', 'studio.rebase'))
INVENTORY.update(_rows('studio', H, 'software installation/download remains separately reviewed',
                       'studio.install_package'))
INVENTORY.update(_rows('studio', N, 'interactive process input/terminal is never an owner escape hatch',
                       'studio.terminal', 'studio.input'))
INVENTORY.update(_rows('studio', A, 'explicit local preview request; loopback/network read rules retained',
                       'studio.web_request'))
INVENTORY.update(_rows('terminal', N, 'no model shell authority', 'terminal.run'))
# Applications and platform.
INVENTORY.update(_rows('application', A, 'application/path literally named in the request',
                       'system.open_application', 'system.open_path', 'system.close_application',
                       'ide.open_workspace', 'ide.open_file'))
INVENTORY.update(_rows('application', R, 'read-only process listing', 'system.list_running_applications'))
INVENTORY.update(_rows('application', H, 'force termination is never an ordinary close',
                       'system.terminate_application'))
INVENTORY.update(_rows('system', A, 'typed user-session API; explicit on/off/level; state restored by caller',
                       'system.audio_set_volume', 'system.audio_set_mute', 'system.bluetooth_set_power'))
INVENTORY.update(_rows('system', R, 'typed read-only status', 'system.audio_status', 'system.bluetooth_status'))
# Desktop control: the native task broker (task_authority) binds each effect.
INVENTORY.update(_rows('desktop', A, 'unified desktop task grant; fresh observation, ledger, Stop',
                       'desktop.activate', 'desktop.launch', 'desktop.focus', 'desktop.invoke', 'desktop.select',
                       'desktop.set_text', 'desktop.toggle', 'desktop.expand', 'desktop.collapse', 'desktop.scroll',
                       'desktop.search', 'desktop.navigate_folder', 'desktop.navigate_settings', 'desktop.media_act',
                       'desktop.visual_click', 'desktop.submit_message', 'desktop.clipboard_write'))
INVENTORY.update(_rows('desktop', R, 'scoped app observation; transient frames only',
                       'desktop.observe', 'desktop.capture', 'desktop.media_list'))
INVENTORY.update(_rows('desktop', A, 'explicit task-bound paste/read only; no background clipboard read',
                       'desktop.clipboard_read'))
INVENTORY.update(_rows('browser', A, 'interactive browser task; explicit navigation/search',
                       'interactive.launch', 'interactive.navigate', 'interactive.new_tab', 'interactive.switch_tab',
                       'interactive.close_tab', 'interactive.act', 'interactive.field_value'))
INVENTORY.update(_rows('browser', R, 'interactive observation', 'interactive.observe', 'interactive.dialog_info'))
INVENTORY.update(_rows('browser', H, 'uploads/downloads/dialog dismissal need explicit resource binding',
                       'interactive.upload', 'interactive.download_artifact', 'interactive.dismiss_dialog'))
INVENTORY.update(_rows('communication', A, 'exact user-bound destination and content; verified client context',
                       'communication.submit'))
# Knowledge, research and web.
INVENTORY.update(_rows('knowledge', R, 'selected or literal document', 'knowledge.read_selected',
                       'knowledge.find_files'))
INVENTORY.update(_rows('knowledge', A, 'explicit add to a named project', 'knowledge.add_to_project'))
INVENTORY.update(_rows('research', R, 'explicit search/research request; public web reads',
                       'research.run', 'web.search', 'web.read', 'web.open', 'web.links', 'web.page_info',
                       'web.follow', 'web.scope'))
INVENTORY.update(_rows('research', A, 'explicit learn/download request; literal URL',
                       'web.learn', 'web.learn_urls', 'web.refresh', 'web.download', 'web.save_download',
                       'web.import_download', 'web.remove'))
# Personal records.
_personal_read = ('calendar.calendars', 'calendar.free_busy', 'calendar.get', 'calendar.range', 'calendar.search',
                  'tasks.get', 'tasks.search', 'reminders.get', 'reminders.history', 'reminders.search',
                  'personal.today')
_personal_write = ('calendar.create', 'calendar.update', 'calendar.save_calendar', 'tasks.create', 'tasks.update',
                   'tasks.complete', 'tasks.reopen', 'tasks.schedule', 'reminders.create', 'reminders.update',
                   'reminders.snooze', 'reminders.dismiss', 'personal.export', 'personal.import_preview',
                   'personal.import_cancel')
_personal_delete = ('calendar.delete', 'calendar.delete_calendar', 'calendar.delete_occurrence', 'tasks.delete',
                    'reminders.delete', 'personal.import_commit')
INVENTORY.update(_rows('personal', R, 'local personal store', *_personal_read))
INVENTORY.update(_rows('personal', A, 'direct explicit create/update/complete of one resolved record',
                       *_personal_write))
INVENTORY.update(_rows('personal', H, 'permanent record deletion/bulk import keep proposal review', *_personal_delete))
INVENTORY.update(_rows('personal', D, 'Contacts/Profile are compatibility controllers, not public features',
                       'contacts.create', 'contacts.delete', 'contacts.duplicates', 'contacts.get', 'contacts.merge',
                       'contacts.merge_preview', 'contacts.resolve', 'contacts.search', 'contacts.update',
                       'profile.avatar', 'profile.get', 'profile.update'))
# Mail.
INVENTORY.update(_rows('mail', R, 'local mail records', 'mail.get', 'mail.search', 'mail.thread', 'mail.folders',
                       'mail.outbox', 'mail.recipients', 'mail.inline_images', 'mail.connections',
                       'mail.cancel', 'mail.cancel_sync', 'mail.import_cancel', 'mail.proposal_cancel',
                       'mail.proposal_prepare'))
INVENTORY.update(_rows('mail', A, 'explicit draft/sync/import/export; literal recipients for send',
                       'mail.prepare', 'mail.reply', 'mail.save_draft', 'mail.discard', 'mail.attach',
                       'mail.calendar_draft', 'mail.from_event', 'mail.retry_rejected', 'mail.update',
                       'mail.create_folder', 'mail.export', 'mail.save_attachment', 'mail.import_preview',
                       'mail.sync', 'mail.fetch_body', 'mail.server_search', 'mail.add_knowledge',
                       'mail.create_event', 'mail.create_task', 'mail.send'))
INVENTORY.update(_rows('mail', H, 'remote mailbox changes/bulk import keep explicit review',
                       'mail.remote_action', 'mail.folder_action', 'mail.sent_copy', 'mail.import_commit',
                       'mail.cache_remove'))
INVENTORY.update(_rows('mail', N, 'connection/credential/security configuration is sensitive',
                       'mail.connection_save', 'mail.connection_state', 'mail.connection_test'))
INVENTORY.update(_rows('media', A, 'explicit local import/render of literal source', 'media.import', 'media.render'))

# Native Linux desktop task effects (task_authority.TaskScope.effect).
NATIVE_EFFECTS = {
    'open': (A, 'installed application resolved from the request'),
    'visit': (A, 'validated URL literal in the request'),
    'read': (R, 'current verified task location'),
    'search': (A, 'literal query'),
    'click': (A, 'uniquely named control with fresh verification'),
    'scroll': (A, 'bounded scroll within the bound window'),
    'tab': (A, 'bounded tab navigation'),
    'edit_save': (A, 'new document; unused literal path; no overwrite'),
    'paste_save': (A, 'explicit task-bound paste; unused literal path'),
    'copy': (A, 'literal source/destination; no overwrite'),
    'move': (A, 'literal source/destination; no overwrite'),
    'send': (A, 'exact destination/content; verified client context; no replay'),
    'draft': (A, 'exact destination/content; submission forbidden'),
}

# Capabilities intentionally absent from the local tool registry.
EXTERNAL_FAMILIES = {
    'connect.remote_ai': (REMOTE_RULES_ONLY, 'C7 exact device grants; never Owner Mode'),
    'connect.files': (REMOTE_RULES_ONLY, 'C5/C8 exact device grants'),
    'connect.studio': (REMOTE_RULES_ONLY, 'C6 exact device grants'),
    'connect.sync': (REMOTE_RULES_ONLY, 'C3 exact device grants'),
    'system.power_session': (OS_AUTH_REQUIRED, 'logind/Polkit decides; OLIVE never bypasses authentication'),
    'system.wifi_toggle': (UNSUPPORTED, 'no typed controller in this milestone'),
    'system.display_brightness': (UNSUPPORTED, 'no supported user-level brightness API detected on this machine'),
    'system.root_operations': (NOT_SAFE_FOR_OWNER_AUTO, 'no root shell, sudo rule or Polkit bypass'),
}


def classify(tool):
    """Return (class, family, binding) or raise for an unclassified tool."""
    try:
        return INVENTORY[tool]
    except KeyError:
        raise LookupError('Unclassified Owner Mode controller: ' + tool) from None


def summary():
    counts = {name: 0 for name in CLASSES}
    for classification, _, _ in INVENTORY.values():
        counts[classification] += 1
    return counts
