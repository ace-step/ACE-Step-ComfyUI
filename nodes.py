import json
import base64
import io
import struct
import wave
import os

import numpy as np
import torch
import requests


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


class AceStepMusicGen:
    """Generate music via ACE-Step OpenRouter-compatible API server."""

    CATEGORY = "api node/audio/AceStep"
    FUNCTION = "generate"
    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "info")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_url": ("STRING", {
                    "default": "https://api.acemusic.ai",
                    "tooltip": "ACE-Step API server base URL",
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Music description / caption",
                }),
            },
            "optional": {
                "lyrics": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Song lyrics (leave empty for instrumental)",
                }),
                "task_type": (["text2music", "cover", "repaint"], {
                    "default": "text2music",
                }),
                "instrumental": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Generate instrumental only (no vocals)",
                }),
                "duration": ("FLOAT", {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 300.0,
                    "step": 1.0,
                    "tooltip": "Audio duration in seconds",
                }),
                "bpm": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 300,
                    "step": 1,
                    "tooltip": "Beats per minute (0 = auto)",
                }),
                "key_scale": ("STRING", {
                    "default": "",
                    "tooltip": "Musical key and scale (e.g. 'C major', 'A minor')",
                }),
                "time_signature": ("STRING", {
                    "default": "",
                    "tooltip": "Time signature (e.g. '4/4', '3/4', '6/8')",
                }),
                "vocal_language": (["en", "zh", "ja", "ko", "es", "fr", "de", "unknown"], {
                    "default": "en",
                }),
                "sample_mode": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Use LLM to generate prompt/lyrics from query",
                }),
                "use_format": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Use LLM to enhance caption and lyrics",
                }),
                "seed": ("STRING", {
                    "default": "-1",
                    "tooltip": "Random seed (-1 = random)",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.85,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                }),
                "guidance_scale": ("FLOAT", {
                    "default": 7.0,
                    "min": 0.0,
                    "max": 20.0,
                    "step": 0.5,
                }),
                "src_audio": ("AUDIO", {
                    "tooltip": "Source audio for cover/repaint tasks",
                }),
                "ref_audio": ("AUDIO", {
                    "tooltip": "Reference audio for style/timbre guidance",
                }),
                "repainting_start": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 300.0,
                    "step": 0.1,
                    "tooltip": "Repaint region start time in seconds",
                }),
                "repainting_end": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 300.0,
                    "step": 0.1,
                    "tooltip": "Repaint region end time in seconds (0 = full length)",
                }),
                "audio_cover_strength": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "Cover strength (1.0 = full cover)",
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API key (auto-saved locally after first input, also reads ACESTEP_API_KEY env var)",
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def generate(
        self,
        server_url,
        prompt,
        lyrics="",
        task_type="text2music",
        instrumental=False,
        duration=30.0,
        bpm=0,
        key_scale="",
        time_signature="",
        vocal_language="en",
        sample_mode=False,
        use_format=False,
        batch_size=1,
        seed="-1",
        temperature=0.85,
        guidance_scale=7.0,
        src_audio=None,
        ref_audio=None,
        repainting_start=0.0,
        repainting_end=0.0,
        audio_cover_strength=1.0,
        api_key="",
    ):
        url = server_url.rstrip("/") + "/v1/chat/completions"

        # Build message content with audio inputs
        # API routing: cover/repaint → audio[0]=src, audio[1]=ref; text2music → audio[0]=ref
        audio_list = []
        if task_type in ("cover", "repaint"):
            if src_audio is not None:
                audio_list.append(src_audio)
            if ref_audio is not None:
                audio_list.append(ref_audio)
        else:
            if ref_audio is not None:
                audio_list.append(ref_audio)

        content = self._build_content(prompt, audio_list)

        # Build request body
        body = {
            "model": "acemusic/acestep-v15-turbo",
            "messages": [{"role": "user", "content": content}],
            "modalities": ["audio"],
            "stream": False,
            "temperature": temperature,
            "guidance_scale": guidance_scale,
            "batch_size": batch_size,
            "task_type": task_type,
            "sample_mode": sample_mode,
            "use_format": use_format,
            "audio_config": {
                "duration": duration,
                "format": "wav",
                "vocal_language": vocal_language,
                "instrumental": instrumental,
            },
        }

        # Seed: "-1" means random, otherwise validate and take the first value
        seed_str = seed.strip().split(",")[0].strip()
        if seed_str and seed_str != "-1":
            try:
                int(seed_str)
            except ValueError:
                raise RuntimeError(f"Invalid seed value: '{seed_str}', must be an integer")
            body["seed"] = seed_str
        if bpm > 0:
            body["audio_config"]["bpm"] = bpm
        body["audio_config"]["key_scale"] = key_scale.strip() or None
        body["audio_config"]["time_signature"] = time_signature.strip() or None
        if lyrics:
            body["lyrics"] = lyrics

        # Repaint/cover specific parameters (only when relevant)
        if task_type == "repaint":
            body["repainting_start"] = repainting_start
            if repainting_end > 0.0:
                body["repainting_end"] = repainting_end
        if task_type == "cover":
            body["audio_cover_strength"] = audio_cover_strength

        # HTTP request – resolve API key: widget input > env var > saved config
        resolved_key = api_key.strip() if api_key else ""
        if resolved_key:
            _save_api_key(resolved_key)
            os.environ["ACESTEP_API_KEY"] = resolved_key
        else:
            resolved_key = os.environ.get("ACESTEP_API_KEY", "") or _load_api_key()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AceMusic-ComfyUI/1.0",
        }
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"

        try:
            resp = requests.post(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=600,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Cannot connect to {server_url}: {e}")
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Request to {server_url} timed out")

        # Parse response
        choices = result.get("choices", [])
        if not choices:
            raise RuntimeError("API returned no choices")

        message = choices[0].get("message", {})
        text_content = message.get("content", "")
        audio_items = message.get("audio", [])

        if not audio_items:
            raise RuntimeError(f"API returned no audio. Response: {text_content}")

        # Decode all audio items and batch them
        waveforms = []
        sample_rate = None
        for item in audio_items:
            audio_url = item.get("audio_url", {}).get("url", "")
            if not audio_url:
                continue
            wf, sr = self._decode_audio_data_url(audio_url)
            # wf shape: (1, channels, samples)
            waveforms.append(wf)
            sample_rate = sr

        if not waveforms:
            raise RuntimeError("API returned no valid audio data")

        # Pad to same length and concat along batch dim
        max_len = max(w.shape[-1] for w in waveforms)
        padded = []
        for wf in waveforms:
            if wf.shape[-1] < max_len:
                pad_size = max_len - wf.shape[-1]
                wf = torch.nn.functional.pad(wf, (0, pad_size))
            padded.append(wf)

        # (N, channels, samples)
        audio_tensor = torch.cat(padded, dim=0)

        return (
            {"waveform": audio_tensor, "sample_rate": sample_rate},
            text_content,
        )

    def _build_content(self, prompt, audio_list):
        """Build message content, optionally with multimodal audio inputs."""
        if not audio_list:
            return prompt

        # Multimodal: text + input_audio(s)
        parts = []

        if prompt:
            parts.append({"type": "text", "text": prompt})

        for audio in audio_list:
            waveform = audio["waveform"].squeeze(0)  # (channels, samples)
            sr = audio["sample_rate"]
            b64 = self._tensor_to_wav_b64(waveform, sr)
            parts.append({
                "type": "input_audio",
                "input_audio": {"data": b64, "format": "wav"},
            })

        return parts

    def _decode_audio_data_url(self, data_url):
        """Decode base64 data URL to torch audio tensor using stdlib wave."""
        if "," in data_url:
            b64_data = data_url.split(",", 1)[1]
        else:
            b64_data = data_url

        audio_bytes = base64.b64decode(b64_data)
        buf = io.BytesIO(audio_bytes)

        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # Use numpy for fast PCM decoding
        if sampwidth == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError(f"Unsupported WAV sample width: {sampwidth}")

        # Interleaved -> (n_frames, n_channels) -> (n_channels, n_frames)
        samples = samples.reshape(n_frames, n_channels).T
        # Add batch dim: (1, n_channels, n_frames)
        tensor = torch.from_numpy(samples).unsqueeze(0)
        return tensor, sample_rate

    def _tensor_to_wav_b64(self, waveform, sample_rate):
        """Encode torch tensor to WAV base64 string using stdlib wave."""
        # waveform shape: (channels, samples)
        n_channels = waveform.shape[0]
        n_frames = waveform.shape[1]

        # Clamp and convert to 16-bit PCM
        clamped = waveform.clamp(-1.0, 1.0)
        pcm = (clamped * 32767).to(torch.int16)

        # Interleave channels: (channels, samples) -> (samples * channels,)
        interleaved = pcm.T.contiguous().reshape(-1)
        raw = struct.pack(f"<{interleaved.numel()}h", *interleaved.tolist())

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(raw)

        return base64.b64encode(buf.getvalue()).decode("utf-8")
