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
 'Studio interactive terminal for Linux is not available in this build yet.': 'Studio interactive terminal for Linux is not available in this build yet.',
 'Windows command shells for Linux is not available in this build yet.': 'Windows command shells are not available on Linux. The bounded Python command runner remains available.',
 'Native application control for Linux is not available in this build yet.': 'Native application control for Linux is not available in this build yet.',
 'File changed since it was read': 'That file changed since OLIVE last read it. Reload it before applying the edit.',
 'Google authorization did not complete. Check desktop-client setup and permissions; credentials were not exposed.': 'Google authorization did not complete. Check the Google desktop-client setup checklist and permissions, then retry.',
 'OLIVE REIMAGINE needs a configured local media engine; no image was generated.': 'OLIVE REIMAGINE needs a configured local media engine; no image was generated.',
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
from ..connect.inference_client import MESSAGES as _REMOTE_AI_MESSAGES
_MESSAGES.update({message: message for message in _REMOTE_AI_MESSAGES.values()})
for _message in (
 'Remote inference failed. No local fallback was used.',
 'Remote AI is text only. Remove attachments before sending; their bytes are not shared.',
 'Remote AI supports OLIVE FAST, NORMAL and MAX. DEEP and REIMAGINE are unavailable remotely.',
 'Action results cannot be regenerated as Remote AI answers.',
 'Finish the current request before changing its target',
):
 _MESSAGES[_message] = _message

def public_error(error):
 from ..services.ollama_service import GenerationOutputLimit, EmptyModelAnswer
 if isinstance(error,GenerationOutputLimit):
  return {'code':'GenerationOutputLimit','message':
      'The model reached its output limit. The partial answer is retained; ask to continue.' if error.visible else
      'The model exhausted its output budget before producing a visible answer. Use a larger response budget or a supported lower-thinking configuration.'}
 if isinstance(error,EmptyModelAnswer):return {'code':'EmptyModelAnswer','message':'The selected model returned no visible answer. No alternative model or canned answer was substituted.'}
 from ..platform_support import PlatformUnavailable
 if isinstance(error,PlatformUnavailable):return {'code':'PlatformUnavailable','message':str(error)}
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
