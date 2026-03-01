import json
import base64
import io
import struct
import wave
import os

import numpy as np
import torch
import requests


# =============================================================================
# Persistent API key storage
# =============================================================================

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".config")
_API_KEY_FILE = os.path.join(_CONFIG_DIR, "api_key")


def _save_api_key(key):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_API_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key)


def _load_api_key():
    try:
        with open(_API_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


# =============================================================================
# HTTP / audio helpers
# =============================================================================

def _resolve_api_key(api_key: str) -> str:
    resolved = api_key.strip() if api_key else ""
    if resolved:
        _save_api_key(resolved)
        os.environ["ACESTEP_API_KEY"] = resolved
    else:
        resolved = os.environ.get("ACESTEP_API_KEY", "") or _load_api_key()
    return resolved


def _make_headers(api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AceMusic-ComfyUI/2.0",
    }
    resolved = _resolve_api_key(api_key)
    if resolved:
        headers["Authorization"] = f"Bearer {resolved}"
    return headers


def _post_json(url: str, body: dict, headers: dict, timeout: int = 600) -> dict:
    try:
        resp = requests.post(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot connect to server: {e}")
    except requests.exceptions.Timeout:
        raise RuntimeError("Request timed out")


def _tensor_to_wav_b64(waveform, sample_rate) -> str:
    n_channels = waveform.shape[0]
    clamped = waveform.clamp(-1.0, 1.0)
    pcm = (clamped * 32767).to(torch.int16)
    interleaved = pcm.T.contiguous().reshape(-1)
    raw = struct.pack(f"<{interleaved.numel()}h", *interleaved.tolist())
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _encode_audio_b64(audio) -> str:
    waveform = audio["waveform"].squeeze(0)
    return _tensor_to_wav_b64(waveform, audio["sample_rate"])


def _parse_wav_bytes(audio_bytes: bytes):
    """Parse WAV bytes manually to support PCM (fmt=1) and float32 (fmt=3)."""
    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise RuntimeError("Not a valid WAV file")
    pos = 12
    fmt_tag = n_channels = sample_rate = sampwidth = 0
    data_offset = data_size = 0
    while pos < len(audio_bytes) - 8:
        chunk_id = audio_bytes[pos:pos+4]
        chunk_size = struct.unpack_from("<I", audio_bytes, pos+4)[0]
        pos += 8
        if chunk_id == b"fmt ":
            fmt_tag = struct.unpack_from("<H", audio_bytes, pos)[0]
            n_channels = struct.unpack_from("<H", audio_bytes, pos+2)[0]
            sample_rate = struct.unpack_from("<I", audio_bytes, pos+4)[0]
            sampwidth = struct.unpack_from("<H", audio_bytes, pos+14)[0] // 8
        elif chunk_id == b"data":
            data_offset = pos
            data_size = chunk_size
            break
        pos += chunk_size
    if data_offset == 0:
        raise RuntimeError("WAV data chunk not found")
    raw = audio_bytes[data_offset:data_offset + data_size]
    n_frames = data_size // (n_channels * sampwidth)
    if fmt_tag == 1:  # PCM int
        if sampwidth == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError(f"Unsupported PCM sample width: {sampwidth}")
    elif fmt_tag == 3:  # IEEE float32
        samples = np.frombuffer(raw, dtype=np.float32).copy()
    else:
        raise RuntimeError(f"Unsupported WAV format tag: {fmt_tag}")
    samples = samples.reshape(n_frames, n_channels).T
    tensor = torch.from_numpy(samples).unsqueeze(0)
    return tensor, sample_rate


def _decode_audio_data_url(data_url: str):
    if "," in data_url:
        b64_data = data_url.split(",", 1)[1]
    else:
        b64_data = data_url
    audio_bytes = base64.b64decode(b64_data)
    return _parse_wav_bytes(audio_bytes)


def _parse_audio_response(result: dict):
    choices = result.get("choices", [])
    audio_items = []
    text_content = ""
    if choices:
        message = choices[0].get("message", {})
        text_content = message.get("content", "")
        audio_items = message.get("audio", [])
    else:
        audio_items = result.get("audio", [])
        text_content = json.dumps(result.get("metadata", {}), ensure_ascii=False)
        if result.get("lyrics"):
            text_content += f"\n\nLyrics:\n{result['lyrics']}"
    if not audio_items:
        raise RuntimeError(
            f"API returned no audio. Response: {text_content or json.dumps(result)}"
        )
    waveforms = []
    sample_rate = None
    for item in audio_items:
        url = ""
        if isinstance(item, dict):
            url = item.get("audio_url", {}).get("url", "") or item.get("url", "")
        if not url:
            continue
        wf, sr = _decode_audio_data_url(url)
        waveforms.append(wf)
        sample_rate = sr
    if not waveforms:
        raise RuntimeError("API returned no valid audio data")
    max_len = max(w.shape[-1] for w in waveforms)
    padded = []
    for wf in waveforms:
        if wf.shape[-1] < max_len:
            wf = torch.nn.functional.pad(wf, (0, max_len - wf.shape[-1]))
        padded.append(wf)
    audio_tensor = torch.cat(padded, dim=0)
    return {"waveform": audio_tensor, "sample_rate": sample_rate}, text_content


def _build_multimodal_content(prompt: str, audio_list: list) -> list | str:
    if not audio_list:
        return prompt
    parts = []
    if prompt:
        parts.append({"type": "text", "text": prompt})
    for audio in audio_list:
        b64 = _encode_audio_b64(audio)
        parts.append({
            "type": "input_audio",
            "input_audio": {"data": b64, "format": "wav"},
        })
    return parts


# =============================================================================
# Constants
# =============================================================================

VALID_LANGUAGES = [
    "en", "zh", "ja", "ko", "es", "fr", "de", "pt", "ru", "it",
    "ar", "az", "bg", "bn", "ca", "cs", "da", "el", "fa", "fi",
    "he", "hi", "hr", "ht", "hu", "id", "is", "la", "lt", "ms",
    "ne", "nl", "no", "pa", "pl", "ro", "sa", "sk", "sr", "sv",
    "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi", "yue",
    "unknown",
]

DEFAULT_CAPTION = (
    "tight and groovy disco-funk track driven by a hyper-articulate slap "
    "bassline weaving syncopated sixteenth-note grooves with percussive thumb "
    "pops and ghost-note textures, locked into a crisp four-on-the-floor drum "
    "machine beat. Clean, funky guitar provides sparse chord stabs to leave "
    "sonic space for the bass, while filtered synth pads swell subtly in the "
    "background. The smooth male lead vocal glides over the infectious groove. "
    "The arrangement builds through verses and catchy choruses, then strips "
    "down to drums and bass for an extended, harmonically adventurous solo "
    "section: the bassist unleashes a technically explosive showcase\u2014rapid "
    "double-thumb slaps morph into tapped harmonics, chromatic walking lines "
    "resolve into chordal double-stops, and envelope-filter sweeps cascade "
    "into distorted octave leaps. After the solo\u2019s climax, wah-drenched funk "
    "guitar re-enters for a call-and-response exchange with the bass before "
    "the full band drops into a final chorus and a gradual fade out, with the "
    "bassline\u2019s final harmonic ringing into silence."
)

DEFAULT_LYRICS = (
    "[Intro]\n"
    "[Heavy guitar riff and drums]\n"
    "[Vocal scream] Yeah!\n"
    "\n"
    "[Guitar Solo]\n"
    "\n"
    "[Verse 1]\n"
    "\n"
    "[Pre-Chorus]\n"
    "\n"
    "[Chorus]\n"
    "\n"
    "[Verse 2]\n"
    "\n"
    "[Pre-Chorus]\n"
    "\n"
    "[Chorus]\n"
    "\n"
    "[Bridge]\n"
    "\n"
    "[Guitar Solo]\n"
    "\n"
    "[Chorus]\n"
    "\n"
    "[Outro]\n"
    "[Song ends abruptly]"
)


# =============================================================================
# Node: Audio Codes (editable passthrough)
# =============================================================================

class AceStepAudioCodes:
    """Editable audio codes passthrough.
    Paste codes manually, or receive from Text2Music Server generation output."""

    CATEGORY = "api node/audio/ACE-Step"
    FUNCTION = "process"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("audio_codes",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_codes": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Audio codes (<|audio_code_N|> tokens). "
                               "Edit manually or receive from audio_codes_in.",
                }),
            },
            "optional": {
                "audio_codes_in": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Auto-fill from Text2Music Server output or paste manually",
                }),
            },
        }

    def process(self, audio_codes="", audio_codes_in=""):
        resolved = audio_codes_in.strip() if audio_codes_in and audio_codes_in.strip() else audio_codes.strip()
        return {"ui": {"audio_codes": [resolved]}, "result": (resolved,)}


# =============================================================================
# Node: Text2music Gen Params
# =============================================================================

class AceStepText2MusicGenParams:
    """Generation parameters for text2music / cover / remix / repaint."""

    CATEGORY = "api node/audio/ACE-Step"
    FUNCTION = "build"
    RETURN_TYPES = ("ACESTEP_GEN_PARAMS",)
    RETURN_NAMES = ("gen_params",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sample_mode": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "ON: use sample_query to let LLM generate caption/lyrics/metadata. "
                               "OFF: use manual caption and lyrics below.",
                }),
                "vocal_language": (VALID_LANGUAGES, {"default": "en"}),
            },
            "optional": {
                "sample_query": ("STRING", {
                    "default": "a funk rock song with groovy bass and punchy drums",
                    "multiline": True,
                    "placeholder": "Describe the music you want (e.g. a funk rock song with groovy bass)",
                    "tooltip": "Natural language description for LLM to generate caption/lyrics/metadata",
                }),
                "is_instrumental": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Generate instrumental only (no vocals).",
                }),
                "caption": ("STRING", {
                    "default": DEFAULT_CAPTION,
                    "multiline": True,
                    "placeholder": "Music style description (e.g. deep house, dreamy, atmospheric)",
                    "tooltip": "Music style description / caption",
                }),
                "lyrics": ("STRING", {
                    "default": DEFAULT_LYRICS,
                    "multiline": True,
                    "placeholder": "Song lyrics with [verse], [chorus] tags... (empty = instrumental)",
                    "tooltip": "Song lyrics (leave empty for instrumental)",
                }),
                "auto": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "ON: bpm/key left for LM to decide. "
                               "OFF: use manual values.",
                }),
                "cover_strength": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Cover strength (only used when src_audio is connected)",
                }),
                "remix_strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Remix noise strength (only used when src_audio is connected)",
                }),
                "is_repaint": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Enable repaint mode (requires src_audio). "
                               "Regenerates a time range within the source audio.",
                }),
                "bpm": ("INT", {
                    "default": 120, "min": 0, "max": 300, "step": 1,
                    "tooltip": "Beats per minute (0 = auto)",
                }),
                "key": ("STRING", {
                    "default": "",
                    "tooltip": "e.g. 'C major', 'D minor'",
                }),
                "duration": ("FLOAT", {
                    "default": 30.0, "min": -1.0, "max": 600.0, "step": 1.0,
                    "tooltip": "Duration in seconds (-1 = model decides)",
                }),
                "time_signature": ("STRING", {
                    "default": "4",
                    "tooltip": "Time signature (e.g. 2, 3, 4, 6). Empty = auto.",
                }),
                "repaint_start": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 600.0, "step": 0.1,
                    "tooltip": "Repaint region start time in seconds",
                }),
                "repaint_end": ("FLOAT", {
                    "default": 0.0, "min": 0.0, "max": 600.0, "step": 0.1,
                    "tooltip": "Repaint region end time in seconds (0 = full length)",
                }),
                "refer_audio": ("AUDIO", {
                    "tooltip": "Reference audio for style/timbre guidance",
                }),
                "src_audio": ("AUDIO", {
                    "tooltip": "Source audio for cover/remix/repaint",
                }),
                "audio_codes": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Audio codes from Audio Codes node",
                }),
            },
        }

    def build(self, sample_mode, vocal_language,
              sample_query="", is_instrumental=False,
              caption=DEFAULT_CAPTION, lyrics=DEFAULT_LYRICS,
              auto=True, cover_strength=0.0, remix_strength=1.0, is_repaint=False,
              bpm=120, key="", duration=30.0, time_signature="4",
              repaint_start=0.0, repaint_end=0.0,
              refer_audio=None, src_audio=None, audio_codes=""):
        codes = audio_codes.strip() if audio_codes else ""
        has_src = src_audio is not None
        has_codes = bool(codes)

        if is_repaint and has_src:
            task_type = "repaint"
        elif has_src or has_codes:
            task_type = "cover"
        else:
            task_type = "text2music"

        if sample_mode:
            instrumental = is_instrumental
        else:
            instrumental = not lyrics.strip()

        return ({
            "task_type": task_type,
            "sample_mode": sample_mode,
            "sample_query": sample_query.strip() if sample_mode else "",
            "caption": caption,
            "lyrics": lyrics,
            "vocal_language": vocal_language,
            "instrumental": instrumental,
            "bpm": 0 if auto else bpm,
            "key_scale": "" if auto else key,
            "duration": -1.0 if auto else duration,
            "time_signature": "" if auto else time_signature,
            "auto_metas": auto,
            "cover_strength": cover_strength,
            "remix_strength": remix_strength,
            "repaint_start": repaint_start,
            "repaint_end": repaint_end,
            "refer_audio": refer_audio,
            "src_audio": src_audio,
            "audio_codes": codes,
        },)


# =============================================================================
# Node: Settings
# =============================================================================

class AceStepSettings:
    """Inference settings: LM + DiT parameters."""

    CATEGORY = "api node/audio/ACE-Step"
    FUNCTION = "build"
    RETURN_TYPES = ("ACESTEP_SETTINGS",)
    RETURN_NAMES = ("settings",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("STRING", {"default": "-1", "tooltip": "-1 = random"}),
                "thinking": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Enable 5Hz LM audio code generation (llm_dit mode)",
                }),
                "use_cot_caption": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "LLM rewrites/enhances caption via CoT",
                }),
                "use_cot_language": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "LLM auto-detects vocal language",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.85, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "LM sampling temperature",
                }),
                "lm_cfg_scale": ("FLOAT", {
                    "default": 2.0, "min": 1.0, "max": 5.0, "step": 0.1,
                    "tooltip": "LM classifier-free guidance scale",
                }),
                "lm_top_p": ("FLOAT", {
                    "default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "LM nucleus sampling top-p",
                }),
                "lm_top_k": ("INT", {
                    "default": 0, "min": 0, "max": 200, "step": 1,
                    "tooltip": "LM top-k sampling (0 = disabled)",
                }),
                "dit_guidance_scale": ("FLOAT", {
                    "default": 7.0, "min": 0.0, "max": 20.0, "step": 0.5,
                    "tooltip": "DiT classifier-free guidance scale",
                }),
                "dit_inference_steps": ("INT", {
                    "default": 8, "min": 1, "max": 200, "step": 1,
                    "tooltip": "DiT diffusion steps (turbo default = 8)",
                }),
                "dit_infer_method": (["ode", "sde"], {
                    "default": "ode",
                    "tooltip": "DiT ODE/SDE inference method",
                }),
            },
        }

    def build(self, seed, thinking, use_cot_caption, use_cot_language,
              temperature, lm_cfg_scale, lm_top_p, lm_top_k,
              dit_guidance_scale, dit_inference_steps, dit_infer_method):
        return ({
            "seed": seed,
            "thinking": thinking,
            "use_cot_caption": use_cot_caption,
            "use_cot_language": use_cot_language,
            "temperature": temperature,
            "lm_cfg_scale": lm_cfg_scale,
            "lm_top_p": lm_top_p,
            "lm_top_k": lm_top_k,
            "dit_guidance_scale": dit_guidance_scale,
            "dit_inference_steps": dit_inference_steps,
            "dit_infer_method": dit_infer_method,
        },)


# =============================================================================
# Shared: build request body for text2music / repaint Server nodes
# =============================================================================

def _build_request_body(gen_params: dict, settings: dict) -> dict:
    gp = gen_params
    st = settings

    is_sample_mode = gp.get("sample_mode", False)
    sample_query = gp.get("sample_query", "")

    audio_list = []
    if gp.get("refer_audio") is not None:
        audio_list.append(gp["refer_audio"])
    if gp.get("src_audio") is not None:
        audio_list.append(gp["src_audio"])

    prompt = sample_query if is_sample_mode else gp.get("caption", "")
    content = _build_multimodal_content(prompt, audio_list)

    task_type = gp.get("task_type", "text2music")
    has_src = gp.get("src_audio") is not None
    has_codes = bool((gp.get("audio_codes", "") or "").strip())
    if task_type == "text2music" and (has_src or has_codes):
        task_type = "cover"

    body = {
        "model": "acemusic/acestep-v15-turbo",
        "messages": [{"role": "user", "content": content}],
        "modalities": ["audio"],
        "stream": False,
        "task_type": task_type,
        "thinking": st.get("thinking", True),
        "temperature": st.get("temperature", 0.85),
        "top_p": st.get("lm_top_p", 0.9),
        "use_cot_caption": st.get("use_cot_caption", True),
        "use_cot_language": st.get("use_cot_language", True),
        "use_cot_metas": gp.get("auto_metas", True),
        "guidance_scale": st.get("dit_guidance_scale", 7.0),
        "audio_config": {
            "format": "wav",
            "vocal_language": gp.get("vocal_language", "en"),
            "instrumental": gp.get("instrumental", False),
        },
    }

    if is_sample_mode:
        body["sample_mode"] = True

    lm_cfg = st.get("lm_cfg_scale")
    if lm_cfg is not None:
        body["lm_cfg_scale"] = lm_cfg
    lm_top_k = st.get("lm_top_k", 0)
    if lm_top_k and lm_top_k > 0:
        body["top_k"] = lm_top_k

    steps = st.get("dit_inference_steps")
    if steps is not None:
        body["inference_steps"] = steps
    method = st.get("dit_infer_method")
    if method:
        body["infer_method"] = method

    duration = gp.get("duration", -1.0)
    if duration and duration > 0:
        body["audio_config"]["duration"] = duration

    bpm = gp.get("bpm", 0)
    if bpm and bpm > 0:
        body["audio_config"]["bpm"] = bpm

    key_scale = (gp.get("key_scale", "") or "").strip()
    if key_scale:
        body["audio_config"]["key_scale"] = key_scale

    time_sig = gp.get("time_signature", "")
    if time_sig:
        body["audio_config"]["time_signature"] = time_sig

    lyrics = gp.get("lyrics", "")
    if lyrics and not is_sample_mode:
        body["lyrics"] = lyrics

    seed_str = str(st.get("seed", "-1")).strip().split(",")[0].strip()
    if seed_str and seed_str != "-1":
        try:
            int(seed_str)
        except ValueError:
            raise RuntimeError(f"Invalid seed: '{seed_str}'")
        body["seed"] = seed_str

    # Cover/remix: server handles audio2code internally
    if task_type == "cover":
        body["thinking"] = False
        body["use_cot_caption"] = False
        body["use_cot_language"] = False
        body["use_cot_metas"] = False
        rs = gp.get("remix_strength", 1.0)
        if rs is not None:
            body["audio_cover_strength"] = rs
        cs = gp.get("cover_strength", 0.0)
        if cs is not None and cs > 0:
            body["cover_noise_strength"] = cs

    # Repaint: LM is not used
    if task_type == "repaint":
        body["thinking"] = False
        body["use_cot_caption"] = False
        body["use_cot_language"] = False
        body["use_cot_metas"] = False
        body["repainting_start"] = gp.get("repaint_start", 0.0)
        rend = gp.get("repaint_end", 0.0)
        if rend and rend > 0:
            body["repainting_end"] = rend

    audio_codes = gp.get("audio_codes", "")
    if body.get("thinking", False):
        pass
    elif audio_codes:
        body["audio_codes"] = audio_codes

    return body


# =============================================================================
# Node: Text2music Server
# =============================================================================

class AceStepText2MusicServer:
    """Text2music / cover / remix / repaint server.
    Inputs: serve_config fields + gen_params + settings.
    Outputs: audio + info + audio_codes."""

    CATEGORY = "api node/audio/ACE-Step"
    FUNCTION = "generate"
    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "info", "audio_codes")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["cloud", "local"], {"default": "cloud"}),
                "server_url": ("STRING", {"default": "https://api.acemusic.ai"}),
                "gen_params": ("ACESTEP_GEN_PARAMS", {}),
                "settings": ("ACESTEP_SETTINGS", {}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def generate(self, mode, server_url, gen_params, settings, api_key=""):
        url = server_url.strip()
        if not url:
            url = "http://127.0.0.1:8002" if mode == "local" else "https://api.acemusic.ai"
        base = url.rstrip("/")
        headers = _make_headers(api_key)

        body = _build_request_body(gen_params, settings)
        result = _post_json(f"{base}/v1/chat/completions", body, headers)
        audio, text_content = _parse_audio_response(result)

        out_codes = ""
        choices = result.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            out_codes = msg.get("audio_codes", "") or ""
        return (audio, text_content, out_codes)


# =============================================================================
# Node: Show Text (minimal text display, no external dependencies)
# =============================================================================

class AceStepShowText:
    """Display any STRING input as text."""

    CATEGORY = "api node/audio/ACE-Step"
    FUNCTION = "show"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            },
        }

    def show(self, text):
        return {"ui": {"text": [text]}, "result": (text,)}
