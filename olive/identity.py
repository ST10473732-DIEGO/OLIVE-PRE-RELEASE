"""Current identity and narrow compatibility resolution; no data relocation."""
import json,os,sys
from pathlib import Path
IDENTITY=json.loads(Path(__file__).with_name('identity.json').read_text(encoding='utf-8'))
APP_NAME=IDENTITY['name']
APP_VERSION=IDENTITY['version']


def normalize_environment(environ=None):
    env=os.environ if environ is None else environ
    for old in list(env):
        if not old.startswith('DMDO_'):continue
        new='OLIVE_'+old[5:]
        legacy=env[old];current=env.get(new)
        if current and legacy and current!=legacy:
            same_path=False
            if new in {'OLIVE_DATA_DIR','OLIVE_PYTHON'}:
                same_path=Path(current).expanduser().resolve()==Path(legacy).expanduser().resolve()
            if not same_path:raise ValueError(f'Conflicting {new} and {old}; select one explicit configuration')
        if not current and legacy:env[new]=legacy
    return env


def resolve_profile(environ=None,home=None,platform=None):
    env=normalize_environment(dict(os.environ if environ is None else environ))
    if env.get('OLIVE_DATA_DIR'):return Path(env['OLIVE_DATA_DIR']).expanduser().resolve()
    base=Path.home() if home is None else Path(home)
    current=base/IDENTITY['default_directory'];legacy=base/IDENTITY['legacy_directory']
    # Nonempty unknown state also deserves an explicit decision, never overwrite.
    occupied=lambda p:p.exists() and (not p.is_dir() or any(p.iterdir()))
    if occupied(current) and occupied(legacy) and current.resolve()!=legacy.resolve():
        raise ValueError('Both OLIVE and legacy DMDO profile locations contain data. Set OLIVE_DATA_DIR explicitly; nothing was merged or moved.')
    default=current
    if (platform or sys.platform).startswith('linux'):
        xdg=Path(env.get('XDG_DATA_HOME',''))
        default=(xdg if xdg.is_absolute() else base/'.local'/'share')/'olive'
        if occupied(default) and any(occupied(p) and p.resolve()!=default.resolve() for p in (current,legacy)):
            raise ValueError('Multiple OLIVE profile locations contain data. Set OLIVE_DATA_DIR explicitly; nothing was merged or moved.')
    if occupied(legacy):return legacy.resolve()
    if occupied(current):return current.resolve()
    return default.resolve()


def display_alias(value):
    known={"DMDO-"+role:"OLIVE-"+role for role in ("CHAT","FAST","REASONING","CODING","VISION","EMBEDDINGS")}
    return known.get(value,value)
