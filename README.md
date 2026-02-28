# ACE-Step-ComfyUI

ComfyUI nodes for [ACE-Step](https://acemusic.ai) AI music generation — text-to-music, cover/remix, repaint, and LLM-powered sample generation.

## Installation

### Via ComfyUI Manager

Search for **ACE-Step-ComfyUI** in ComfyUI Manager and install.

### Manual Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ace-step/ACE-Step-ComfyUI.git
cd ACE-Step-ComfyUI
pip install -r requirements.txt
```

Restart ComfyUI after installation.

## Setup

### Cloud Mode (default)

1. Get your API key from [acemusic.ai/api-key](https://acemusic.ai/api-key)
2. In the **Text2music Server** node, set **mode** → `cloud` and paste your key into **api_key**
3. Or set the environment variable `ACESTEP_API_KEY`

> The key is auto-saved locally (in `.config/` under the node directory) and displayed as `●●●●` for security. It is **not** stored in workflow JSON.

### Local Mode

Local mode lets you run the ACE-Step inference server on your own machine (requires a GPU with sufficient VRAM).

**1. Install ACE-Step 1.5**

```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
```

Install dependencies (choose one):

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

**2. Start the local server**

```bash
# Using uv
uv run acestep-openrouter --host 0.0.0.0 --port 8002

# Or if installed via pip
acestep-openrouter --host 0.0.0.0 --port 8002
```

The server will download model weights on first launch and then listen on `http://127.0.0.1:8002`.

**3. Configure ComfyUI**

In the **Text2music Server** node, set **mode** → `local`. The URL auto-fills to `http://127.0.0.1:8002` and the **api_key** field is hidden since no key is needed locally.

## Usage Guide

Drag `workflows/text2music.json` into ComfyUI to load the ready-to-use workflow.

```
                             ┌── refer_audio ──┐
Load Audio (refer) ──────────┘                 │
                                               ▼
                            Text2music Gen Params ── gen_params ──► Text2music Server ──► Save Audio
                                               ▲                          ▲          │
Load Audio (src) ──── src_audio ───────────────┘                   Settings ┘      Show Text
Audio Codes ────────── audio_codes ────────────┘
```

### Quick Start: Text-to-Music

1. Open the workflow. **sample_mode** is OFF by default — you are in manual mode.
2. Fill in **caption** (music style description) and **lyrics** (with `[verse]`, `[chorus]` tags). Leave lyrics empty for instrumental.
3. Click **Queue Prompt**. The generated audio appears in **Save Audio** and generation info in **Show Text**.

### Sample Mode (LLM Auto-Generation)

Instead of writing caption and lyrics yourself, let the LLM generate everything from a simple description:

1. Toggle **sample_mode** → ON in the Gen Params node.
2. Fill in **sample_query** (e.g. `"a funk rock song with groovy bass and punchy drums"`).
3. Choose **vocal_language** and set **is_instrumental** if you want instrumental only.
4. Click **Queue Prompt**. The LLM generates caption, lyrics, bpm, key, duration, and time signature automatically, then synthesizes the music.

> In sample mode, only three fields are shown: `sample_query`, `vocal_language`, and `is_instrumental`. All other parameters are decided by the LLM.

### Manual Mode Controls

When **sample_mode** is OFF, you have full manual control:

| Field | Description |
|-------|-------------|
| **caption** | Music style / genre description |
| **lyrics** | Song lyrics (empty = instrumental) |
| **vocal_language** | Language for vocals |
| **auto** | ON (default): let the LM decide bpm, key, duration, time signature. OFF: set them manually below. |
| **bpm** | Beats per minute (shown when auto=OFF) |
| **key** | Musical key, e.g. `C major` (shown when auto=OFF) |
| **duration** | Duration in seconds (shown when auto=OFF) |
| **time_signature** | e.g. `4`, `3`, `6` (shown when auto=OFF) |
| **is_repaint** | Enable repaint mode (see below) |
| **cover_strength** | Noise injection strength for cover (0 = clean cover) |
| **remix_strength** | How much original audio to preserve (1.0 = full) |

### Cover / Remix Mode

1. Load the source song via **Load Audio** and connect it to Gen Params → `src_audio`.
2. Alternatively, connect pre-extracted audio codes via **Audio Codes** → Gen Params → `audio_codes`.
3. The task type automatically switches to `cover` when `src_audio` or `audio_codes` is connected.
4. Adjust **cover_strength** and **remix_strength** to control the output.

> The server automatically converts source audio to audio codes internally when needed. The generated `audio_codes` are also returned as a third output of Text2music Server.

### Repaint Mode

1. Connect source audio to Gen Params → `src_audio`.
2. Toggle **is_repaint** → ON. The **repaint_start** and **repaint_end** fields appear.
3. Set the time range (in seconds) for the region to regenerate.
4. Fill in **caption** and **lyrics** for the regenerated section.

### Reference Audio

Connect a reference audio file to Gen Params → `refer_audio` to guide the style and timbre of the generated music. This works with any mode.

### Settings Node

The **Settings** node controls inference hyperparameters:

| Field | Default | Description |
|-------|---------|-------------|
| **seed** | `-1` | Random seed (`-1` = random, set a number for reproducibility) |
| **thinking** | `true` | Enable 5Hz LM audio code generation (higher quality, slower) |
| **use_cot_caption** | `true` | LM chain-of-thought for caption refinement |
| **use_cot_language** | `true` | LM chain-of-thought for language detection |
| **temperature** | `0.85` | Sampling temperature |
| **lm_cfg_scale** | `1.0` | LM classifier-free guidance scale |
| **dit_guidance_scale** | `3.5` | DiT guidance scale |
| **dit_inference_steps** | `60` | Number of DiT denoising steps |

## Node Reference

| Node | Description | Inputs | Outputs |
|------|-------------|--------|---------|
| **Text2music Gen Params** | Build generation parameters. Supports sample_mode (LLM auto) and manual mode. | `sample_mode`, `vocal_language`, + optional fields | `gen_params` |
| **Settings** | Inference hyperparameters for LM + DiT. | `seed`, `thinking`, `temperature`, etc. | `settings` |
| **Text2music Server** | Calls the ACE-Step API to generate music. | `gen_params`, `settings`, `server_url`, `api_key`, `mode` | `audio`, `info`, `audio_codes` |
| **Audio Codes** | Editable passthrough for audio codes. Paste manually or receive from Text2music Server. | `audio_codes_in` (optional) | `audio_codes` |
| **Show Text** | Displays any STRING input as a read-only text area. | `text` | `text` (passthrough) |

## Tips

- **Cover/Repaint auto-safety:** When the task is `cover` or `repaint`, `thinking`, `use_cot_caption`, and `use_cot_language` are forced to `false` regardless of Settings values — the LM is not used for these tasks.
- **Auto metas:** When `auto` is ON, the LM infers bpm/key/duration/time_signature. When OFF, your manual values are sent directly.
- Use **Show Text** nodes connected to `info` outputs to inspect what the server returned (LLM-generated parameters, generation metadata, etc.).

## License

[MIT](LICENSE)
