"""Human-readable approval summaries from trusted action fields, never model prose parsing."""


def approval_presentation(value, services=None):
    arguments = value.get("arguments", {})
    if value['tool_name'] == 'connect.request':
        if arguments.get('capability') == 'models.remote':
            info = arguments['inference']
            return dict(action='Remote AI · OLIVE ' + info['preset'].upper(), targets=[arguments['source_name']],
                content=f"{info['message_count']} visible messages · {info['input_bytes']} bytes of context",
                scope='This exact authenticated text request only.',
                consequence='Uses this device’s local model. No tools or private context. Saved permission remains Ask.')
        return dict(action=value['summary'], targets=[arguments['target_name']],
            content='Read-only Connect operation from ' + arguments['source_name'],
            scope='This exact authenticated request only.',
            consequence='Saved permission remains Ask. No content or inference access.')
    if value['tool_name'].startswith('mail.'):
        from ..mail.presentation import approval
        return approval(value['tool_name'],arguments,services)
    if services and hasattr(services,'personal'):
        from ..personal.contracts import SPEC,MAIN_ONLY
        if value['tool_name'] in SPEC|MAIN_ONLY:
            from ..personal.presentation import approval
            return approval(value['tool_name'],arguments,services.personal)
    if value['tool_name'] in {'terminal.execute','system.open_application'} and 'file_hashes' in arguments:
        return {
            'action':value['summary'],
            'targets':[str(p) for p in arguments.get('arguments',[])] or [str(arguments.get('executable',''))],
            'content':'Executable: '+str(arguments.get('executable',''))+'\nArguments: '+repr(arguments.get('arguments',[])),
            'scope':'One new owned process tree. Inspection and input need separate permissions; no unrelated windows are inspected.',
            'consequence':'Runs this selected local code with your account permissions, not in an execution sandbox. Cancel prevents launch. File changes invalidate this approval.',
        }
    if value['tool_name'] == 'desktop.inspect_application' and 'scope' in arguments:
        return {'action':value['summary'],'content':str(arguments['scope']),
                'scope':str(arguments['scope']),'consequence':str(arguments.get('consequence','Read application metadata'))}
    if value['tool_name'] == 'terminal.run':
        return {
            'action': 'Run the reviewed local command',
            'targets': [str(arguments.get('working_directory', ''))],
            'content': str(arguments.get('command', '')),
            'scope': f"One {arguments.get('environment', 'local')} command, with a maximum runtime of {arguments.get('timeout', 30)} seconds.",
            'consequence': 'Executes this command with your local account permissions. The working directory is not a filesystem or network sandbox. Cancel prevents execution; stopping later cannot undo earlier effects.',
        }
    if value["tool_name"] in {"web.learn", "web.learn_urls", "web.scope", "web.refresh", "web.remove"}:
        urls = arguments.get("urls", [])
        if services and value["tool_name"] == "web.learn":
            session = services.research.repository.load_all().get(arguments.get("session_id"))
            selected = arguments.get("source_ids", [])
            urls = [source.url for source in session.sources if source.id in selected] if session else []
        elif services and value["tool_name"] in {"web.refresh", "web.remove"}:
            source = services.research.sources.load_all().get(arguments.get("source_id"))
            urls = [source.url] if source else []
        removing = value["tool_name"] == "web.remove"
        scoping = value["tool_name"] == "web.scope"
        return {
            "action": {"web.learn": "Save reviewed research sources to Knowledge", "web.learn_urls": "Learn the selected website pages", "web.scope": "Preview the website scope", "web.refresh": "Refresh the saved website source", "web.remove": "Remove the local website source"}[value["tool_name"]],
            "targets": [str(url)[:4096] for url in urls[:30]],
            "content": "\n".join(str(url)[:4096] for url in urls[:30]) or "The selected source is no longer available; cancel this request.",
            "scope": ("Preview a bounded website scope." if scoping else "Remove the selected local web source." if removing else
                      f"Selected sources only. Collection: {arguments.get('collection', 'existing collection')}."),
            "consequence": ("Removes the local record and its index entries; the original website is unchanged." if removing else
                            "May contact the selected website to discover links. This does not authorise learning the resulting scope." if scoping else
                            "May contact these websites and store their content in local Knowledge. Source content remains untrusted. Cancel prevents this operation from starting."),
        }
    if value["tool_name"] == "workspace.run_validation":
        commands = arguments.get("commands", [])
        content = "\n".join(
            f"{command['name']}: {command['executable']} {' '.join(command['arguments'])}"
            for command in commands
        ) or "No standard test commands detected."
        return {
            "action": "Run the detected project checks",
            "content": content,
            "scope": "One validation in the approved workspace, using the commands shown. Each command has a bounded runtime.",
            "consequence": "Executes project code with the workspace's existing trust policy. Tests and builds may write files or access resources allowed by that policy. Cancel prevents these commands from starting; stopping after execution cannot undo earlier effects.",
        }
    # Exclude credential-shaped fields. Important ordinary content is readable without JSON.
    fields = ("application", "target", "action", "path", "url", "destination", "recipient", "to", "subject", "body", "text", "content", "files", "object", "setting", "old_value", "new_value", "source", "publisher", "cost", "expected", "query", "command", "package", "manager")
    content = "\n".join(f"{key.replace('_', ' ').title()}: {str(arguments[key])[:12000]}" for key in fields if key in arguments)
    if arguments.get('window_identity'):
        window = arguments['window_identity']
        content += f"\nTarget window: {window.get('title','')}\nProcess: {window.get('pid')}\nExecutable: {window.get('executable','')}"
    return {
        "action": value["summary"], "content": content or "No additional content supplied.",
        "scope": f"One {value['tool_name']} operation; risk level {value['risk_level']}.",
        "consequence": "Approving authorises this exact action. Cancel prevents it from starting. Technical details contain the full arguments.",
    }
