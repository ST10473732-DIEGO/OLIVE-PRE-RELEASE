"""Authorise a local preview only for a listener owned by an active RunSession."""
from urllib.parse import urlsplit
import ipaddress
import psutil
from .workspace_service import require_approved_workspace


def authorize(services,session_id):
    run=services.run_service.sessions.get(session_id)
    if not run or run.state!='running' or not run.process_id:
        raise ValueError('Start a local web application before opening its preview')
    require_approved_workspace(services.workspace_repo,run.workspace_id)
    url=urlsplit(run.local_url or '')
    if url.scheme not in {'http','https'} or url.username or url.password or not url.port or url.hostname not in {'127.0.0.1','localhost','::1'}:
        raise ValueError('The run has no supported loopback preview origin')
    owned=services.run_service._processes.get(run.id)
    if owned is None or owned.pid!=run.process_id or owned.returncode is not None:
        raise ValueError('The run process is no longer owned by this runtime')
    try:
        parent=psutil.Process(run.process_id)
        processes=[parent,*parent.children(recursive=True)]
        found=any(connection.status==psutil.CONN_LISTEN and connection.laddr.port==url.port
                  and (ipaddress.ip_address(connection.laddr.ip).is_loopback or connection.laddr.ip in {'0.0.0.0','::'})
                  for process in processes for connection in process.net_connections(kind='inet'))
    except (psutil.Error,OSError,ValueError) as error:
        raise ValueError('Could not verify ownership of the local preview listener') from error
    if not found:raise ValueError('The preview port is not owned by this RunSession')
    return {'session_id':run.id,'workspace_id':run.workspace_id,'url':run.local_url}
