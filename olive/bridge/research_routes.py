"""Explicit research presentation operations; existing tools bear network policy."""

ACTIVE_METHODS = frozenset({
    'interaction.research', 'research.resume', 'research.learn_urls', 'research.scope',
    'research.save_sources', 'research.refresh_web', 'research.remove_web',
    'research.download', 'research.read_download', 'research.import_download',
    'research.export_download',
})


def history(s, query="", offset=0):
    from .history_page import summary_page
    keys = ('id', 'question', 'project_id', 'status', 'activity', 'updated_at')
    return summary_page(s.research.history(), keys, "question", query, offset)


def routes(s):
    return {
        'interaction.research': s.interaction.research_question,
        'research.history': lambda **args: history(s, **args),
        'research.get': s.research.get,
        'research.current': lambda: {'session': (s.research.preparing_session or s.research.orchestrator.current).to_dict() if (s.research.preparing_session or s.research.orchestrator.current) else None,
                                    'active': bool(s.research.starting or s.research.orchestrator.active)},
        'research.preferences': s.research.preferences,
        'research.pause': s.research.pause,
        'research.cancel': s.research.cancel,
        'research.resume': s.research.resume,
        'research.save_sources': s.research.save_sources,
        'research.save_report': s.research.save_report,
        'research.scope': s.research.scope,
        'research.learn_urls': s.research.learn_urls,
        'research.web_sources': s.research.web_sources,
        'research.web_source': s.research.web_source,
        'research.refresh_web': s.research.refresh_web,
        'research.remove_web': s.research.remove_web,
        'research.downloads': s.research.downloads,
        'research.download': s.research.download,
        'research.read_download': s.research.read_download,
        'research.remove_download': s.research.remove_download,
        'research.import_download': s.research.import_download,
        'research.export_download': s.research.export_download,
        'research.clear_cache': s.research.clear_cache,
    }
