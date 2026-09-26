"""Bounded conversation options on the existing controller and repositories."""
import asyncio


def metadata(s, chat_id, title, notes, project_id):
    if chat_id in s.interaction.active or s.interaction.interpreting.get(chat_id):
        raise ValueError('Stop the active request before changing its context')
    context = s.interaction.contexts.get(chat_id)
    project_id = project_id or None
    if project_id and project_id not in s.project_repo.load_all():
        raise ValueError('Unknown project')
    if context and context.pending and project_id != s.chats[chat_id].project_id:
        raise ValueError('Resolve the pending action before changing this conversation project')
    value = s.chat.update(chat_id, title=title, notes=notes, project_id=project_id)
    if context:
        context.project_id = project_id
        if project_id:
            context.entities['project'] = s.project_repo.load_all()[project_id].title
        else:
            context.entities.pop('project', None)
    return value


def search(s, query):
    from ..application.chat_controller import last_line
    query = query.strip().casefold()
    records = []
    for chat in sorted(s.chats.values(), key=lambda c: c.updated_at, reverse=True):
        match = next((m.content for m in chat.messages if query and query in m.content.casefold()), '')
        if not query or query in chat.title.casefold() or match:
            position = match.casefold().find(query) if match else 0
            records.append({'id': chat.id, 'title': chat.title, 'excerpt': match[max(0,position-40):position+160],
                            'updated_at': chat.updated_at, 'last': last_line(chat)})
        if len(records) == 100:
            break
    return records


async def summarize(s, tasks, chat_id):
    if chat_id in tasks or chat_id in s.chat.generations or chat_id in s.interaction.active or s.interaction.interpreting.get(chat_id):
        raise ValueError('Finish the current conversation work before summarising')
    tasks[chat_id] = asyncio.current_task()
    try:
        return await s.chat.summarize(chat_id)
    finally:
        tasks.pop(chat_id, None)


def delete(s, tasks, chat_id):
    if chat_id in tasks:
        raise ValueError('Cancel the summary before deleting this conversation')
    return s.chat.delete(chat_id)


def delete_all(s, tasks):
    if tasks:
        raise ValueError('Cancel the running summary before deleting all conversations')
    return s.chat.delete_all()


def cancel_summary(tasks, chat_id):
    task = tasks.get(chat_id)
    if task:
        task.cancel()
    return {'cancellation_requested': bool(task)}


def routes(s, tasks):
    return {
        'chat.metadata': lambda **args: metadata(s, **args),
        'chat.search': lambda query: search(s, query),
        'chat.delete': lambda chat_id: delete(s, tasks, chat_id),
        'chat.delete_all': lambda: delete_all(s, tasks),
        'chat.remove_image': s.chat.remove_image,
        'chat.summarize': lambda chat_id: summarize(s, tasks, chat_id),
        'chat.cancel_summary': lambda chat_id: cancel_summary(tasks, chat_id),
        'chat.summary_state': lambda chat_id: {'active': chat_id in tasks},
        'interaction.inspect': s.interaction.inspect,
    }
