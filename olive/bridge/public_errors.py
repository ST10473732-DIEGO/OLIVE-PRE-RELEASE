"""Allowlisted user guidance; provider/model exception text stays private."""
_MESSAGES = {
 'secure_identity_unavailable': 'The secure device key is unavailable. Unlock the system credential store and try again. OLIVE will not replace an existing key.',
 'pairing_comparison_mismatch': 'Pairing comparison did not match. Create a new pairing session.',
 'pairing_expired': 'Pairing expired. Create a new pairing session.',
 'identity_recovery_required': 'The device identity requires recovery. Its key will not be replaced automatically.',
 'capability_unavailable': 'This capability is not available for this device.',
 'device_not_paired': 'This device is not paired or its access has been revoked.',
 'network_disabled': 'Turn Connect on using an explicitly selected local interface first.',
 'device_offline': 'This device is offline.',
 'connection_failed': 'Could not connect. Check the paired identity, selected local interface and Connect port.',

 'The configured local ComfyUI runtime is missing': 'The configured local ComfyUI runtime is missing. Check the local media installation.',
 'The configured local ComfyUI runtime exited during startup': 'The local ComfyUI runtime could not start. Check its Python/CUDA dependencies and local model setup.',
 'File changed since it was read': 'That file changed since OLIVE last read it. Reload it before applying the edit.',
 'Google authorization did not complete. Check desktop-client setup and permissions; credentials were not exposed.': 'Google authorization did not complete. Check the Google desktop-client setup checklist and permissions, then retry.',
 "This OLIVE preset's local model is unavailable. Wait for Models to finish checking, or inspect Advanced Settings.": "This OLIVE preset's local model is unavailable. Wait for Models to finish checking, or inspect Advanced Settings.",
 'Task cancelled by user': 'The action was cancelled before execution.',
 'The terminal is not running': 'This terminal has exited. Start the program again before typing.',
 'This workspace already has a running program': 'This workspace already has a running program. Stop it before starting another.',
 'Action was not approved': 'The action was not approved. No action was executed.',
 'Wait for current requests to finish before restoring.': 'Wait for current requests to finish before restoring.',
 'Save or reconcile unsaved Studio files before restoring.': 'Save or discard unsaved Studio files before restoring.',
 'Stop active work before restoring': 'Stop active work before restoring.',
 'Restore complete. Restart OLIVE before further work.': 'Restore complete. Restart OLIVE before further work.',
 'Save or reconcile unsaved editor buffers before changing workspace history': 'Save or discard unsaved editor buffers before changing workspace history.',
 'Approve the repository root before using its Git operations': 'Open and approve the repository root before using its Git operations.',
 'An index upgrade is already active': 'An index upgrade is already active. Cancel it or wait for it to finish.',
 'The preview port is not owned by this RunSession': 'The preview port is not owned by this RunSession. Start the intended local app through Studio.',
 'The run has no supported loopback preview origin': 'This run has no supported local web preview. Its output is still available in Studio.',
 'Stop the current request before changing its objective or context.': 'Stop the current request before changing its objective or context.',
}
from ..platform_support import PLATFORM_LABELS as _PLATFORMS, unavailable_message as _unavailable
for _label in _PLATFORMS.values():
 # Same text require_windows raises when a tool boundary re-wraps it.
 for _feature in ('Studio interactive terminal', 'Native application control'):
  _MESSAGES[_unavailable(_feature, _label)] = _unavailable(_feature, _label)
 _MESSAGES[_unavailable('Windows command shells', _label)] = (
  f'Windows command shells are not available on {_label}. The bounded Python command runner remains available.')
from ..connect.inference_client import MESSAGES as _REMOTE_AI_MESSAGES
_MESSAGES.update({message: message for message in _REMOTE_AI_MESSAGES.values()})
for _message in (
 'Chat research is available on This device only.',
 'Insufficient context for the original request, constraints and evidence. Narrow the selected context or start a new conversation; nothing was silently truncated.',
 'Insufficient context to summarize history safely. Start a new conversation with the required constraints.',
 'OLIVE UNCENSORED has no installed local model available.',
 'OLIVE UNCENSORED requires an Ollama server on this device.',
 'Remote AI supports OLIVE FAST, NORMAL and MAX. UNCENSORED, DEEP and REIMAGINE are unavailable remotely.',
 'Remote inference failed. No local fallback was used.',
 'Remote AI is text only. Remove attachments before sending; their bytes are not shared.',
 'Remote AI supports OLIVE FAST, NORMAL and MAX. DEEP and REIMAGINE are unavailable remotely.',
 'Action results cannot be regenerated as Remote AI answers.',
 'Finish the current request before changing its target',
 'OLIVE media presets generate media and do not use text inference.',
 'Wait for attached documents to finish indexing, or remove failed attachments',
 'Remove an attached image before adding another reference',
 'Cannot verify media GPU release. Reconnect the configured engine, or disconnect it in Media tools while it is running and idle, before retrying Chat.',
):
 _MESSAGES[_message] = _message

def public_error(error):
 from ..services.now_weather import NowError
 if isinstance(error, NowError):return {"code":"Now_" + error.code,"message":str(error)}
 from ..services.media_errors import MediaError
 if isinstance(error, MediaError):
  if error.detail:
   import logging
   logging.getLogger('olive.media').info('Media request failed (%s): %s', error.code, error.detail)
  return {"code":"Media_" + error.code,"message":str(error)}
 import ollama
 if isinstance(error,ollama.ResponseError):
  status = error.status_code if type(error.status_code) is int and 100 <= error.status_code <= 599 else None
  return {'code':'LocalInferenceError','message':'The local inference provider rejected or failed this request'+(f' (HTTP {status})' if status else '')+'. No replacement model or canned answer was used.'}
 from ..services.ollama_service import GenerationOutputLimit, EmptyModelAnswer
 if isinstance(error,GenerationOutputLimit):
  return {'code':'GenerationOutputLimit','message':
      'The model reached its output limit. The partial answer is retained; ask to continue.' if error.visible else
      'The model exhausted its output budget before producing a visible answer. Use a larger response budget or a supported lower-thinking configuration.'}
 if isinstance(error,EmptyModelAnswer):return {'code':'EmptyModelAnswer','message':'The selected model returned no visible answer. No alternative model or canned answer was substituted.'}
 from ..platform_support import PlatformUnavailable
 if isinstance(error,PlatformUnavailable):return {'code':'PlatformUnavailable','message':str(error)}
 from ..notes.service import NotesError
 if isinstance(error,NotesError):return {'code':'NotesError','message':str(error)[:300]}
 from ..draw.service import DrawError
 if isinstance(error,DrawError):return {'code':'DrawError','message':str(error)[:300]}
 from ..personal.errors import PersonalOperationError
 from ..studio_tooling.errors import StudioToolingError
 if isinstance(error,PersonalOperationError):return {'code':'PersonalOperationError','message':str(error)}
 if isinstance(error,StudioToolingError):return {'code':'StudioToolingError','message':str(error)[:2000]}
 message=_MESSAGES.get(str(error)) if isinstance(error,(ValueError,PermissionError,RuntimeError)) else None
 if not message:
  if isinstance(error, FileNotFoundError):message='A required file or executable was not found. Check the selected file and configured toolchain.'
  elif isinstance(error, TimeoutError):message='The request timed out. Check the local provider and current activity before retrying.'
  elif isinstance(error, ConnectionError):message='The connection to the provider was lost. Check that it is running before retrying.'
  elif isinstance(error, PermissionError):message='OLIVE does not have permission for this action. Review its permissions before trying again.'
 return {'code':type(error).__name__,'message':message or 'The request could not complete. Review its inputs, permissions, or current file version.'}
