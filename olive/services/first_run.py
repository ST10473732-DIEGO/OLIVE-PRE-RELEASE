"""First-run setup state, repair detection and end-of-setup verification.

Reported states (runtime.setup_status):

    first_launch     a new profile; the wizard opens
    incomplete       the wizard was started and not finished (resumes at its step)
    complete         verification passed for the chosen package
    skipped          the person chose "Set up later"
    existing         this profile was in use before setup existed; nothing is forced
    requires_repair  something that verified earlier is now missing, or setup.json is unreadable

Setup is never marked complete because downloads finished: only verify() completes it,
and only when every feature of the chosen package that this build can provide works,
including a tiny FAST generation when FAST was set up.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import runtime_manifest as manifests
from ..storage.setup_state_repository import PROFILES, STEPS, SetupStateRepository

log = logging.getLogger(__name__)
NAME_LIMIT = 120


def initialise(profile) -> dict:
    """Decide new versus existing once, before anything else writes into the profile."""
    repository = SetupStateRepository(profile)
    if repository.exists():
        return repository.load()[0]
    existing = SetupStateRepository.profile_in_use(profile)
    state = repository.default('existing' if existing else 'not_started')
    state['origin'] = 'existing-profile' if existing else 'new'
    from ..identity import APP_VERSION
    state['product_version'] = APP_VERSION
    state['updated_at'] = time.time()
    try:
        repository.save(state)
    except OSError:
        log.warning('setup.json could not be written; first-run state is recomputed next start')
    return state


class FirstRunService:
    def __init__(self, services, installer):
        self.s = services
        self.installer = installer
        self.repository = SetupStateRepository(services.data_dir)
        self._system = None
        self.last_verification = None

    # ------------------------------------------------------------------ status
    def _repairs(self, state, located, tags) -> list[dict]:
        """Features that verified at completion and no longer have what they need."""
        if state['state'] != 'complete' or not state['profile']:
            return []
        repairs = []
        manifest = self.installer.manifest()
        verified = set(state['verified_features'])
        for feature in manifests.profile_features(manifest, state['profile']):
            if feature['id'] not in verified:
                continue
            for slot in feature.get('requires', []):
                row = self.installer._slot(slot, located, tags)
                if row['action'] in ('present', 'different_build'):
                    continue
                if row['entry']['kind'] == 'ollama-model' and tags is None:
                    continue  # Ollama is not answering yet; that is not proof the model is gone.
                repairs.append({'feature': feature['id'], 'label': feature['label'], 'slot': slot,
                                'action': row['action'], 'detail': row['detail']})
        return repairs

    async def status(self) -> dict:
        state, readable = self.repository.load()
        located = await asyncio.to_thread(self.s.runtime_discovery.resolve)
        tags = await self.installer.model_tags() if readable and state['state'] == 'complete' else None
        repairs = self._repairs(state, located, tags) if readable else []
        if not readable:
            reported, reason = 'requires_repair', 'unreadable_state'
        elif repairs:
            reported, reason = 'requires_repair', 'missing_components'
        else:
            reported = {'not_started': 'first_launch', 'in_progress': 'incomplete'}.get(state['state'], state['state'])
            reason = None
        manifest = self.installer.manifest()
        return {
            'state': reported, 'reason': reason, 'stored_state': state['state'] if readable else None,
            'step': state['step'], 'profile': state['profile'], 'optional': state['optional'],
            'origin': state['origin'], 'repairs': repairs, 'verified_features': state['verified_features'],
            'completed_at': state['completed_at'],
            'preferred_name': str(self.s.settings.get('preferred_name', '') or ''),
            'target': self.installer.target, 'manifest_source': manifest.get('_source', 'release'),
            'packaged': self.s.runtime_discovery.snapshot()['packaged'],
            'runtimes': {name: value.to_dict(self.s.runtime_discovery.platform) for name, value in located.items()},
            'installed': sorted(state['installed']),
            'job': self.installer.progress(),
        }

    # ------------------------------------------------------------------ updates
    def update(self, step=None, profile=None, preferred_name=None, action=None, optional=None) -> dict:
        state, readable = self.repository.load()
        now = time.time()
        if action == 'reset':
            # Run setup again. An unreadable file is kept beside the new one, never overwritten.
            if not readable:
                self.repository.set_aside(time.strftime('%Y%m%d-%H%M%S'))
                state, readable = self.repository.default('in_progress'), True
            installed = state['installed']
            state = self.repository.default('in_progress')
            state.update(installed=installed, started_at=now, origin='new')
        elif not readable:
            raise ValueError('setup.json is unreadable. Choose "Start setup again" to keep it aside and continue.')
        # Opening, browsing or leaving setup never undoes a verified setup; choosing a
        # different package does (it must verify again).
        if action == 'skip':
            if state['state'] != 'complete':
                state['state'] = 'skipped'
        elif action == 'resume' or (state['state'] in ('not_started', 'existing', 'skipped') and (step or profile)):
            if state['state'] != 'complete':
                state['state'] = 'in_progress'
            state['started_at'] = state['started_at'] or now
        elif action not in (None, 'reset'):
            raise ValueError('Unknown setup action')
        previous = state['profile']
        if step is not None:
            if step not in STEPS:
                raise ValueError('Unknown setup step')
            state['step'] = step
        if profile is not None:
            if profile not in PROFILES:
                raise ValueError('Unknown OLIVE package')
            state['profile'] = profile
        if optional is not None:
            state['optional'] = [str(v) for v in optional][:32]
        if preferred_name is not None:
            name = ' '.join(preferred_name.split())
            if len(name) > NAME_LIMIT:
                raise ValueError(f'Your name can be at most {NAME_LIMIT} characters')
            # Saved only when it changes, so an existing name is never rewritten by a revisit.
            if name != (self.s.settings.get('preferred_name') or ''):
                self.s.settings['preferred_name'] = name
                self.s.settings_repo.save(self.s.settings)
        if state['state'] == 'complete' and profile is not None and profile != previous:
            state['state'] = 'in_progress'  # A different package is not verified yet.
        state['updated_at'] = now
        self.repository.save(state)
        return {'state': state['state'], 'step': state['step'], 'profile': state['profile']}

    # ------------------------------------------------------------------ system
    async def system(self, refresh=False) -> dict:
        if self._system is None or refresh:
            from . import system_check
            self._system = await asyncio.to_thread(system_check.snapshot, None, None,
                                                   self.installer.models_directory())
        return self._system

    # ------------------------------------------------------------------ verify
    async def _fast_smoke(self, model: str) -> dict:
        from .runtime_installer import InstallError, _loopback_host
        try:
            host = _loopback_host(self.s.ollama.host)
        except InstallError as error:
            return {'state': 'failed', 'detail': str(error)}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10), trust_env=False) as client:
                response = await client.post(host + '/api/generate', json={
                    'model': model, 'prompt': 'Reply with the single word: ready', 'stream': False, 'think': False,
                    'options': {'num_predict': 16, 'temperature': 0}})
            text = response.json().get('response', '') if response.status_code == 200 else ''
        except (httpx.HTTPError, ValueError) as error:
            return {'state': 'failed', 'detail': f'The test answer failed: {type(error).__name__}'}
        if not text.strip():
            return {'state': 'failed', 'detail': f'The model did not answer (HTTP {response.status_code})'}
        return {'state': 'passed', 'detail': f'Answered in {time.monotonic() - started:.1f} s', 'sample': text.strip()[:40]}

    async def verify(self, profile: str, run_fast=True, media_smoke=False) -> dict:
        if profile not in PROFILES:
            raise ValueError('Unknown OLIVE package')
        if self.installer.running():
            raise ValueError('Wait for installation to finish before verifying')
        # Refresh what is on this computer: runtime locations, then the model inventory.
        self.s.runtimes = await asyncio.to_thread(self.s.runtime_discovery.resolve, True)
        try:
            await self.s.refresh_model_inventory()
            self.s.publish_model_state()
        except Exception:
            log.exception('Model inventory refresh during verification failed')
        plan = await self.installer.plan(profile)
        manifest = self.installer.manifest()
        results = []
        declared = {f['id']: f for f in manifest['features']}
        for feature in plan['features']:
            row = {'id': feature['id'], 'label': feature['label'], 'state': 'ready', 'detail': ''}
            if not declared[feature['id']].get('requires'):
                # Nothing to install or test: part of OLIVE itself (Connect World still needs a relay).
                row.update(state='built_in', detail=declared[feature['id']].get('note') or '')
            elif feature['state'] == 'not_in_build':
                row.update(state='not_in_build', detail='Not yet available in this build')
            elif feature['state'] == 'external':
                row.update(state='needs_you', detail='Install the missing part yourself, then verify again')
            elif feature['state'] != 'ready':
                row.update(state='optional' if feature['optional_component'] else 'missing',
                           detail='Optional, not installed' if feature['optional_component']
                           else 'Missing: ' + ', '.join(feature['missing']))
            results.append(row)
        fast = next((r for r in results if r['id'] == 'fast'), None)
        smoke = None
        if fast and fast['state'] == 'ready' and run_fast:
            model = next(e['ollama']['model'] for e in manifests.providers(manifest, 'model-fast', None) if e.get('ollama'))
            smoke = await self._fast_smoke(model)
            if smoke['state'] != 'passed':
                fast.update(state='failed', detail=smoke['detail'])
            else:
                fast['detail'] = smoke['detail']
        media = {'state': 'not_run', 'detail': 'Optional; try REIMAGINE, AUDIO or VIDEO in Chat'} if media_smoke else None
        # Something only the person can install (the macOS Ollama app, VoiceStudio) blocks completion
        # only when a Core feature needs it; Creator and Complete extras are reported, not blocking.
        core = {f['id'] for f in plan['features'] if f['profile'] == 'core'}
        blocking = [r for r in results if r['state'] in ('missing', 'failed')
                    or (r['state'] == 'needs_you' and r['id'] in core)]
        ok = not blocking
        state, readable = self.repository.load()
        if readable:
            state['verified_features'] = [r['id'] for r in results if r['state'] in ('ready', 'built_in')]
            if ok:
                state.update(state='complete', step='connect' if state['step'] in ('verify', 'models', 'runtimes') else state['step'],
                             profile=profile, completed_at=time.time())
            elif state['state'] == 'complete':
                state['state'] = 'in_progress'
            state['updated_at'] = time.time()
            self.repository.save(state)
        self.last_verification = {'ok': ok, 'profile': profile, 'features': results, 'fast': smoke, 'media': media,
                                  'some_unavailable': plan['some_unavailable'], 'checked_at': time.time()}
        return self.last_verification
