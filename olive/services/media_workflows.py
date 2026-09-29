"""Fixed, reviewed ComfyUI workflows for Chat media and deterministic routing.

Each workflow names the exact installed files and trusted node classes it
needs, and the ComfyUI versions where it passed a real local acceptance run.
A workflow is routable only when the running engine lists every file, exposes
every node from the expected module and is a validated version. Nothing here
downloads, uploads or accepts a caller-supplied graph.
"""
from dataclasses import dataclass, field
import re

# Node class -> accepted python_module prefixes reported by /object_info.
BUILTIN = ('nodes', 'comfy_extras.')
GGUF = ('custom_nodes.ComfyUI-GGUF-Loader',)


@dataclass(frozen=True)
class Workflow:
    key: str
    kind: str                     # image | video
    label: str                    # Public family label (no filenames)
    operations: frozenset         # generate | edit | text
    files: dict                   # (node class, input) -> exact filename
    nodes: dict                   # node class -> accepted module prefixes
    validated: frozenset = frozenset()   # ComfyUI versions with a passing real run
    blocked: str = ''             # Diagnostic when installed but unusable
    max_references: int = 0
    defaults: dict = field(default_factory=dict)


KLEIN = Workflow(
    'flux2-klein-9b', 'image', 'FLUX.2 Klein', frozenset({'generate', 'edit'}),
    {('UNETLoader', 'unet_name'): 'flux-2-klein-9b-fp8.safetensors',
     ('CLIPLoader', 'clip_name'): 'qwen_3_8b_fp4mixed.safetensors',
     ('VAELoader', 'vae_name'): 'flux2-vae.safetensors'},
    dict.fromkeys(('UNETLoader', 'CLIPLoader', 'VAELoader', 'CLIPTextEncode', 'ConditioningZeroOut',
                   'EmptyFlux2LatentImage', 'Flux2Scheduler', 'CFGGuider', 'KSamplerSelect', 'RandomNoise',
                   'SamplerCustomAdvanced', 'VAEDecode', 'SaveImage', 'LoadImage', 'ImageScaleToTotalPixels',
                   'GetImageSize', 'VAEEncode', 'ReferenceLatent'), BUILTIN),
    frozenset({'0.35.0'}), max_references=1,
    # From ComfyUI's bundled "Image Edit (Flux.2 Klein 9B Distilled)" template.
    defaults={'width': 1024, 'height': 1024, 'steps': 4, 'cfg': 1.0, 'sampler': 'euler', 'megapixels': 1.0})

QWEN = Workflow(
    'qwen-image-2.1', 'image', 'Qwen-Image', frozenset({'generate', 'edit', 'text'}),
    {('UNETLoader', 'unet_name'): 'qwen_image_2.1_int8_convrot.safetensors',
     ('CLIPLoader', 'clip_name'): 'qwen3vl_8b_int8_convrot.safetensors',
     ('VAELoader', 'vae_name'): 'qwen_image_2.1_vae_bf16.safetensors'},
    dict.fromkeys(('UNETLoader', 'CLIPLoader', 'VAELoader', 'TextEncodeQwenImageEditPlus', 'KSampler',
                   'EmptySD3LatentImage', 'ModelSamplingAuraFlow', 'VAEDecode', 'SaveImage'), BUILTIN),
    # 2026-09-29 acceptance on ComfyUI 0.35.0: VAELoader misdetects the 2.1 VAE
    # as WanVAE (state_dict size mismatch) and model detection has no Qwen-Image
    # 2.1 transformer layout. It stays installed and routable once validated.
    validated=frozenset(),
    blocked='Installed ComfyUI 0.35.0 cannot load the Qwen-Image 2.1 VAE/transformer layout',
    max_references=1)

SDXL = Workflow(
    'sdxl-base', 'image', 'SDXL', frozenset({'generate'}),
    {('CheckpointLoaderSimple', 'ckpt_name'): 'sd_xl_base_1.0.safetensors'},
    dict.fromkeys(('CheckpointLoaderSimple', 'CLIPTextEncode', 'EmptyLatentImage', 'KSampler', 'VAEDecode',
                   'SaveImage'), BUILTIN),
    frozenset({'0.35.0'}),
    defaults={'width': 1024, 'height': 1024, 'steps': 20, 'cfg': 7.0})

LTX_NEGATIVE = ('missing limbs, deformities, speaking, music, singing, background music, low quality, idle movement, '
                'low motion,  talking, text or fonts,  foreign characters, ascii, emojis, printed words, blank screens,  '
                'hard cuts between scenes, all of these things are banned. ')
LTX = Workflow(
    'ltx-2.3-t2av', 'video', 'LTX', frozenset({'generate'}),
    {('LTXV23ModelsLoader', 'unet_name'): 'ltxv23_uncensored_v1.4_Q4_K_M.gguf',
     ('LTXV23ModelsLoader', 'text_encoder_name'): 'gemma-3-12b-it-ablit-norms-biproj-Q4_K_M.gguf',
     ('LTXV23ModelsLoader', 'projections_name'): 'ltxv23_uncensored_v1.4_projections.safetensors',
     ('LTXV23ModelsLoader', 'video_vae_name'): 'ltxv23_uncensored_v1.4_video_vae.safetensors',
     ('LTXV23ModelsLoader', 'audio_vae_name'): 'ltxv23_uncensored_v1.4_audio_vae.safetensors',
     ('LatentUpscaleModelLoader', 'model_name'): 'ltx-2.3-spatial-upscaler-x2-1.1.safetensors'},
    {**dict.fromkeys(('LTXV23ModelsLoader', 'LTXV23ImgToVideo', 'LTXV23KSampler'), GGUF),
     **dict.fromkeys(('LTXVSeparateAVLatent', 'LatentUpscaleModelLoader', 'LTXVLatentUpsampler', 'VAEDecode',
                      'VAEDecodeAudio', 'CreateVideo', 'SaveVideo'), BUILTIN)},
    frozenset({'0.35.0'}),
    # The user's manually validated LTXV23_v1.4_T2AV_Q4_FIXED workflow. Image
    # input was bypassed there, so image-to-video is not offered.
    defaults={'width': 768, 'height': 448, 'length': 49, 'fps': 24, 'steps': 8, 'cfg': 1.0,
              'sampler': 'euler', 'schedule': 'distilled (8 steps)', 'image_strength': 0.89})

IMAGE_WORKFLOWS = (QWEN, KLEIN, SDXL)
VIDEO_WORKFLOWS = (LTX,)
WORKFLOWS = {w.key: w for w in IMAGE_WORKFLOWS + VIDEO_WORKFLOWS}

# Preference order per request shape. SDXL is compatibility only: it is never
# an instruction editor and never outranks a validated newer engine.
ROUTES = {
    'edit': ('qwen-image-2.1', 'flux2-klein-9b'),
    'text': ('qwen-image-2.1', 'flux2-klein-9b', 'sdxl-base'),
    'generate': ('flux2-klein-9b', 'qwen-image-2.1', 'sdxl-base'),
}
TEXT_RENDERING = re.compile(
    r'''(?:\b(?:that|which) (?:says|reads)\b|\bwith (?:the )?(?:text|words?|title|caption|headline|slogan)\b|'''
    r'''\b(?:typography|lettering|logo text|poster|sign|banner|label)\b.*["“'][^"”']{2,}["”']|["“][^"”]{2,}["”])''', re.I)


def request_shape(prompt, references):
    if references:
        return 'edit'
    return 'text' if TEXT_RENDERING.search(prompt or '') else 'generate'


def availability(workflow, engine):
    """Return ('ready'|reason) for one workflow on one inspected engine."""
    if engine is None:
        return 'engine not inspected'
    for (node, name), filename in workflow.files.items():
        if filename not in engine['inputs'].get((node, name), ()):
            return 'model missing: ' + filename
    for node, modules in workflow.nodes.items():
        module = engine['modules'].get(node)
        if not module or not module.startswith(modules):
            return 'workflow node unavailable: ' + node
    if workflow.blocked and engine['version'] not in workflow.validated:
        return workflow.blocked
    if engine['version'] not in workflow.validated:
        return f"not validated on ComfyUI {engine['version']}"
    return 'ready'


def route(kind, prompt, references, engine):
    """Choose exactly one validated workflow; never fan out across models."""
    if kind == 'video':
        order, shape = ('ltx-2.3-t2av',), 'generate'
    else:
        shape = request_shape(prompt, references)
        order = ROUTES[shape]
    reasons = {}
    for key in order:
        workflow = WORKFLOWS[key]
        state = availability(workflow, engine)
        if state == 'ready' and len(references) <= workflow.max_references:
            return workflow, shape, reasons
        reasons[key] = state if state != 'ready' else 'too many references'
    return None, shape, reasons


def ltx_frames(length):
    """LTX tiles 8k+1 frames; keep conservative bounds for a 16 GiB GPU."""
    length = max(9, min(int(length), 97))
    return length - (length - 1) % 8


def image_graph(workflow, prompt, seed, prefix, reference=None):
    if workflow.key == 'flux2-klein-9b':
        d = workflow.defaults
        g = {
            'unet': {'class_type': 'UNETLoader', 'inputs': {'unet_name': workflow.files[('UNETLoader', 'unet_name')], 'weight_dtype': 'default'}},
            'clip': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': workflow.files[('CLIPLoader', 'clip_name')], 'type': 'flux2', 'device': 'default'}},
            'vae': {'class_type': 'VAELoader', 'inputs': {'vae_name': workflow.files[('VAELoader', 'vae_name')]}},
            'positive': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['clip', 0]}},
            'negative': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['positive', 0]}},
            'latent': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': d['width'], 'height': d['height'], 'batch_size': 1}},
            'sigmas': {'class_type': 'Flux2Scheduler', 'inputs': {'steps': d['steps'], 'width': d['width'], 'height': d['height']}},
            'guider': {'class_type': 'CFGGuider', 'inputs': {'model': ['unet', 0], 'positive': ['positive', 0], 'negative': ['negative', 0], 'cfg': d['cfg']}},
            'sampler': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': d['sampler']}},
            'noise': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
            'sample': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['noise', 0], 'guider': ['guider', 0], 'sampler': ['sampler', 0], 'sigmas': ['sigmas', 0], 'latent_image': ['latent', 0]}},
            'decode': {'class_type': 'VAEDecode', 'inputs': {'samples': ['sample', 0], 'vae': ['vae', 0]}},
            'save': {'class_type': 'SaveImage', 'inputs': {'images': ['decode', 0], 'filename_prefix': prefix}},
        }
        if reference:
            g['reference'] = {'class_type': 'LoadImage', 'inputs': {'image': reference}}
            g['scaled'] = {'class_type': 'ImageScaleToTotalPixels', 'inputs': {'image': ['reference', 0], 'upscale_method': 'lanczos', 'megapixels': d['megapixels'], 'resolution_steps': 16}}
            g['size'] = {'class_type': 'GetImageSize', 'inputs': {'image': ['scaled', 0]}}
            g['encoded'] = {'class_type': 'VAEEncode', 'inputs': {'pixels': ['scaled', 0], 'vae': ['vae', 0]}}
            g['positive_ref'] = {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': ['positive', 0], 'latent': ['encoded', 0]}}
            g['negative_ref'] = {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': ['negative', 0], 'latent': ['encoded', 0]}}
            g['guider']['inputs'].update(positive=['positive_ref', 0], negative=['negative_ref', 0])
            for key in ('latent', 'sigmas'):
                g[key]['inputs'].update(width=['size', 0], height=['size', 1])
        return g
    if workflow.key == 'sdxl-base':
        d = workflow.defaults
        return {
            'checkpoint': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': workflow.files[('CheckpointLoaderSimple', 'ckpt_name')]}},
            'positive': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['checkpoint', 1]}},
            'negative': {'class_type': 'CLIPTextEncode', 'inputs': {'text': '', 'clip': ['checkpoint', 1]}},
            'latent': {'class_type': 'EmptyLatentImage', 'inputs': {'width': d['width'], 'height': d['height'], 'batch_size': 1}},
            'sample': {'class_type': 'KSampler', 'inputs': {'seed': seed, 'steps': d['steps'], 'cfg': d['cfg'], 'sampler_name': 'euler', 'scheduler': 'normal', 'denoise': 1.0,
                                                           'model': ['checkpoint', 0], 'positive': ['positive', 0], 'negative': ['negative', 0], 'latent_image': ['latent', 0]}},
            'decode': {'class_type': 'VAEDecode', 'inputs': {'samples': ['sample', 0], 'vae': ['checkpoint', 2]}},
            'save': {'class_type': 'SaveImage', 'inputs': {'images': ['decode', 0], 'filename_prefix': prefix}},
        }
    raise ValueError('Workflow has no validated graph')


def video_graph(workflow, prompt, seed, prefix, length=None):
    d, f = workflow.defaults, workflow.files
    frames = ltx_frames(length or d['length'])
    return {
        'models': {'class_type': 'LTXV23ModelsLoader', 'inputs': {
            'unet_name': f[('LTXV23ModelsLoader', 'unet_name')], 'text_encoder_name': f[('LTXV23ModelsLoader', 'text_encoder_name')],
            'projections_name': f[('LTXV23ModelsLoader', 'projections_name')], 'video_vae_name': f[('LTXV23ModelsLoader', 'video_vae_name')],
            'audio_vae_name': f[('LTXV23ModelsLoader', 'audio_vae_name')]}},
        'conditioning': {'class_type': 'LTXV23ImgToVideo', 'inputs': {
            'prompt': prompt, 'negative_prompt': LTX_NEGATIVE, 'width': d['width'], 'height': d['height'], 'length': frames,
            'frame_rate': float(d['fps']), 'batch_size': 1, 'image_strength': d['image_strength'], 'length_from_audio': False,
            'clip': ['models', 1], 'vae': ['models', 2], 'audio_vae': ['models', 3]}},
        'sample': {'class_type': 'LTXV23KSampler', 'inputs': {
            'seed': seed, 'steps': d['steps'], 'cfg': d['cfg'], 'sampler_name': d['sampler'], 'schedule': d['schedule'], 'denoise': 1.0,
            'model': ['models', 0], 'positive': ['conditioning', 0], 'negative': ['conditioning', 1], 'latent_image': ['conditioning', 2]}},
        'separate': {'class_type': 'LTXVSeparateAVLatent', 'inputs': {'av_latent': ['sample', 0]}},
        'upscaler': {'class_type': 'LatentUpscaleModelLoader', 'inputs': {'model_name': f[('LatentUpscaleModelLoader', 'model_name')]}},
        'upscaled': {'class_type': 'LTXVLatentUpsampler', 'inputs': {'samples': ['separate', 0], 'upscale_model': ['upscaler', 0], 'vae': ['models', 2]}},
        'frames': {'class_type': 'VAEDecode', 'inputs': {'samples': ['upscaled', 0], 'vae': ['models', 2]}},
        'audio': {'class_type': 'VAEDecodeAudio', 'inputs': {'samples': ['separate', 1], 'vae': ['models', 3]}},
        'video': {'class_type': 'CreateVideo', 'inputs': {'fps': float(d['fps']), 'bit_depth': 8, 'color_space': 'sRGB', 'images': ['frames', 0], 'audio': ['audio', 0]}},
        'save': {'class_type': 'SaveVideo', 'inputs': {'filename_prefix': prefix, 'format': 'auto', 'format.codec': 'auto',
                                                      'codec': 'auto', 'video': ['video', 0]}},
    }


def combo_options(spec):
    """Options of one /object_info input across legacy and COMBO formats."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return ()
    if isinstance(spec[0], list):
        return tuple(v for v in spec[0] if isinstance(v, str))
    if spec[0] == 'COMBO' and len(spec) > 1 and isinstance(spec[1], dict):
        return tuple(v for v in spec[1].get('options', ()) if isinstance(v, str))
    return ()


def engine_inventory(version, object_info, workflows):
    """The subset of /object_info that routing needs: files and node modules."""
    inputs, modules = {}, {}
    for workflow in workflows:
        for node in workflow.nodes:
            info = object_info.get(node)
            if isinstance(info, dict) and isinstance(info.get('python_module'), str):
                modules[node] = info['python_module']
        for node, name in workflow.files:
            info = object_info.get(node) or {}
            spec = (info.get('input') or {}).get('required', {}).get(name)
            inputs[(node, name)] = combo_options(spec)
    return {'version': version, 'inputs': inputs, 'modules': modules}
