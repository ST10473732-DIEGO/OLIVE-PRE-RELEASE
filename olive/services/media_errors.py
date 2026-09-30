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
        'video_duration_invalid': 'Choose a video length of at least half a second. Nothing was generated.',
        'video_duration_too_long': ('OLIVE VIDEO on this computer is limited to {limit} per video. The limit is the '
                                    '"media_video.max_duration_seconds" setting in settings.json in your OLIVE profile. '
                                    'Nothing was generated.'),
        'video_one_image': 'OLIVE VIDEO currently accepts one starting image. Remove the extra images and send again.',
        'video_image_unsupported': 'OLIVE VIDEO on this computer supports text prompts only. Remove the image and describe the video in text.',
        'video_assembly_unavailable': ('Videos longer or shorter than one native segment (about 2 seconds) need FFmpeg on this '
                                       'computer. OLIVE does not install it. Nothing was generated.'),
        'video_storage_full': 'This computer does not have enough free disk space for this video. Free some space or choose a shorter length. Nothing was generated.',
        'video_segment_invalid': 'A generated video segment did not match the planned format, so the video was not completed. Nothing was saved.',
        'video_assembly_failed': 'OLIVE could not join the video segments. Nothing was saved; details are in the local log.',
        'video_verify_failed': 'The finished video did not pass verification, so it was not saved.',
    }

    def __init__(self, code, detail='', **values):
        self.code = code
        self.detail = str(detail)[:500]  # Internal diagnostics; never shown in Chat.
        # Only OLIVE-computed values (limits) are formatted in; never peer text.
        super().__init__(self.MESSAGES[code].format(**values) if values else self.MESSAGES[code].replace('{limit}', 'its configured maximum'))
