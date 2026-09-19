"""Provider policy at the consequence boundary, independent of model intent."""
from pathlib import PureWindowsPath
import re
from urllib.parse import urlsplit


def require_supported_ui_sender(session, url=''):
    window=getattr(session,'window',None) or {}
    identity=getattr(session,'identity',None)
    names=[getattr(identity,'display_name',''),window.get('application',''),
           PureWindowsPath(window.get('executable','')).stem]
    discord=any(re.fullmatch(r'discord(?:[ _-]?(?:canary|ptb|development))?',str(name),re.I) for name in names)
    title=window.get('title','')
    discord=discord or bool(re.search(r'(?:^|[|—–-]\s*)discord(?:\s+(?:canary|ptb))?\s*$',title,re.I))
    host=(urlsplit(url).hostname or '').lower() if url else ''
    discord=discord or host in {'discord.com','discordapp.com'} or host.endswith(('.discord.com','.discordapp.com'))
    if discord:
        raise PermissionError('Personal Discord messages must be sent manually. Use the configured bot transport for reviewed bot messages; UI automation cannot submit this message.')
