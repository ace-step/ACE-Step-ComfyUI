# ACE-Step-ComfyUI

Official ComfyUI node for [ACE-Step](https://acemusic.ai) AI music generation via ACE-Step API.

## Features

- **Text to Music** — Generate music from text descriptions and lyrics
- **Cover** — Create cover versions from source audio with style control
- **Repaint** — Regenerate specific sections of an audio track


## Installation

### Via ComfyUI Manager

Search for `ACE-Step-ComfyUI` in ComfyUI Manager and install.

### Manual Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ace-step/ACE-Step-ComfyUI.git
cd ACE-Step-ComfyUI
pip install -r requirements.txt
```

Restart ComfyUI after installation.

## Setup

1. Get your API key from [acemusic.ai](https://acemusic.ai/api-key)
2. Set the key using **one** of these methods:
   - Enter it in the `api_key` widget on the node (auto-saved locally after first input, displayed as `●●●●` for security). The key is **not** stored in workflow JSON, so sharing workflows will not leak your API key
   - Set the environment variable `ACESTEP_API_KEY`

> **Note:** The API key is saved in the `.config/` folder under the node directory. Do not share this folder with others.

## Node: ACE-Step Music Generate

Located in: **api node > audio > AceStep**

### Inputs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| server_url | STRING | `https://api.acemusic.ai` | ACE-Step API server URL |
| prompt | STRING | | Music description / caption |
| lyrics | STRING | | Song lyrics (leave empty for instrumental) |
| task_type | ENUM | `text2music` | `text2music`, `cover`, or `repaint` |
| instrumental | BOOLEAN | `false` | Generate instrumental only |
| duration | FLOAT | `30.0` | Audio duration in seconds (1–300) |
| bpm | INT | `0` | Beats per minute (0 = auto) |
| key_scale | STRING | | Musical key and scale (e.g. `C major`) |
| time_signature | STRING | | Time signature (e.g. `4/4`, `3/4`) |
| vocal_language | ENUM | `en` | Vocal language |
| sample_mode | BOOLEAN | `false` | Use LLM to generate prompt/lyrics from query |
| use_format | BOOLEAN | `false` | Use LLM to enhance caption and lyrics |
| seed | STRING | `-1` | Random seed (-1 = random, comma-separated for batch) |
| temperature | FLOAT | `0.85` | Sampling temperature |
| guidance_scale | FLOAT | `7.0` | Guidance scale |
| src_audio | AUDIO | | Source audio for cover/repaint tasks |
| ref_audio | AUDIO | | Reference audio for style/timbre guidance |
| api_key | STRING | | API key (auto-saved locally) |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| audio | AUDIO | Generated audio waveform |
| info | STRING | Text response from the API |

## License

[MIT](LICENSE)
