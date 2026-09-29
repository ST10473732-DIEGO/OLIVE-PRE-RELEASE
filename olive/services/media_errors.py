"""Allowlisted public failures for Chat media generation.

Exact engine/provider diagnostics stay in logs and job records; Chat receives
one of these stable messages so failures are specific without leaking paths,
queue identities or stack traces.
"""


class MediaError(ValueError):
    MESSAGES = {
        'image_not_configured': 'OLIVE REIMAGINE needs setup: no local image engine is installed. No image was generated.',
        'audio_not_configured': 'OLIVE AUDIO needs setup: no local speech service is configured. No audio was generated.',
        'video_not_configured': 'OLIVE VIDEO needs setup: no local video engine is installed. No video was generated.',
        'audio_model_missing': 'OLIVE AUDIO needs setup: the local speech service has no installed voice model. OLIVE does not download models. No audio was generated.',
        'audio_exposed': 'OLIVE AUDIO is paused: the local speech service is also listening on the network. Restart it bound to 127.0.0.1 only. No text was sent and no audio was generated.',
        'audio_unverified': 'OLIVE AUDIO could not verify that the local speech service listens on this device only. No text was sent and no audio was generated.',
        'engine_start_failed': 'The local media engine could not start. Check its runtime installation; nothing was generated.',
        'engine_unreachable': 'The local media engine is not responding. Check that it is running on this device; nothing was generated.',
        'engine_busy': 'The local media engine is busy with another job. Wait for it to finish, then retry.',
        'engine_incompatible': 'The local media engine is running with settings OLIVE cannot manage safely. Restart it through OLIVE; nothing was generated.',
        'workflow_missing': 'The required local media workflow is not available in the installed engine. Nothing was generated.',
        'model_missing': 'A required local media model is not installed. OLIVE does not download models. Nothing was generated.',
        'unsupported_attachment': 'This mode cannot use the attached file type. Attach a PNG, JPEG, WebP or BMP image, or remove the attachment.',
        'attachment_unsupported_mode': 'This mode does not use attachments yet. Remove the attachment and describe the result in text.',
        'too_many_references': 'Attach one reference image for this edit. Multiple references are not supported by the installed workflow.',
        'cancelled': 'Generation stopped. No media artifact was saved.',
        'no_artifact': 'The engine finished without producing a media file. Nothing was saved.',
        'artifact_missing': 'This media file is no longer available on this device.',
        'gpu_release_unverified': 'GPU release could not be verified, so OLIVE did not start another heavy model. Check the local media engine, then retry.',
        'gpu_busy': 'Another application is holding local models on the GPU. Release them, then retry.',
        'generation_failed': 'The local media engine reported an error. Nothing was saved; details are in the local engine log.',
        'timeout': 'Local media generation took too long and was stopped. Nothing was saved.',
        'remote_unavailable': 'OLIVE REIMAGINE, AUDIO and VIDEO run on This device only. Select This device to generate media; nothing was sent to the paired device.',
        'prompt_required': 'Describe what OLIVE should create.',
        'prompt_too_long': 'Keep media requests under 4,000 characters.',
        'audio_unsupported': 'OLIVE AUDIO creates spoken audio only. Singing, music, sound effects and voice cloning are not available on this device.',
        'speech_text_required': 'Say what OLIVE should speak, for example: Say: Welcome to OLIVE.',
        'speech_too_long': 'Keep speech text under 4,000 characters.',
        'regenerate_unsupported': 'Send the media request again to create a new artifact. Regeneration of media is not supported.',
    }

    def __init__(self, code, detail=''):
        self.code = code
        self.detail = str(detail)[:500]  # Internal diagnostics; never shown in Chat.
        super().__init__(self.MESSAGES[code])
