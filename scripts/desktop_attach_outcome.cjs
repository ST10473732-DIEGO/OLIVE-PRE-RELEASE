// Shared by the live capture harness and ordinary regression tests.
// The first failure is immutable; teardown has a separate evidence channel.
function recordFailure(result, stage, error) {
  if (!result.primary_error) result.primary_error = { stage, error: String(error) };
}
function terminalOutcome({ failure, alerts = [], state, approval, closed, expired }) {
  if (failure) return { kind: 'failure', detail: failure };
  if (alerts.length) return { kind: 'failure', detail: alerts.join('\n') };
  if (closed) return { kind: 'failure', detail: 'Electron closed before attachment completed' };
  if (state?.stopped || state?.session?.status === 'CANCELLED') return { kind: 'cancelled' };
  if (state?.observation?.window) return { kind: 'observation' };
  if (state?.session?.status === 'PAUSED_REVIEW_REQUIRED') return { kind: 'failure', detail: 'Attachment requires review' };
  if (approval) return { kind: 'approval_pending', detail: approval };
  if (expired) return { kind: 'timeout', detail: 'Bounded attachment wait expired' };
  return null;
}
function selectedLaunch(launches, selected, resume, application = 'm2_desktop_acceptance_window.py') {
  const matches = launches.filter(item => item.launch_id === selected);
  if (matches.length !== 1 || (!resume && matches[0].state !== 'launched_not_inspected'))
    throw Error('Select the reviewed launch in Electron before capture');
  if (matches[0].application !== application)
    throw Error('The reviewed acceptance target was not selected');
  return matches[0];
}
function inspectionPolicies(settings, accessible) {
  if (!settings.enabled || !settings.uia || settings.screen_observation || settings.vision_fallback ||
      settings.mouse_policy !== 'deny' || settings.keyboard_policy !== (accessible ? 'ask' : 'deny') ||
      settings.unknown_app_policy !== 'ask') throw Error('Review the isolated test policies before capture');
}
module.exports = { recordFailure, terminalOutcome, selectedLaunch, inspectionPolicies };
