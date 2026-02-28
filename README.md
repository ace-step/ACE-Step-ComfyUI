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
2. In any Server node, set **mode** → `cloud` and paste your key into **api_key**
3. Or set the environment variable `ACESTEP_API_KEY`

### Local Mode

1. Start the ACE-Step OpenRouter server locally:
   ```bash
   cd ACE-Step-1.5
   uv run acestep-openrouter --host 0.0.0.0 --port 8002
   ```
2. In any Server node, set **mode** → `local`
3. The URL auto-fills to `http://127.0.0.1:8002`; **api_key** and **Get API Key** button are hidden in local mode

## Workflows

Two ready-to-use workflow files are provided. Drag any `.json` file into ComfyUI to load it.

| File | Use Case |
|------|----------|
| `workflows/text2music.json` | Text-to-music, cover, remix, and repaint |
| `workflows/example_generate.json` | LLM auto-generates caption/lyrics/metadata, then synthesizes |

### Workflow 1: Text2music / Cover / Remix / Repaint

**`workflows/text2music.json`**

```
Load Audio (refer) ─── refer_audio ──┐
Load Audio (src) ──┬── src_audio ────┤
                   │                 ▼
        audio2code Server    Text2music Gen Params ── gen_params ──► Text2music Server ──► Save Audio
                   │                 ▲                                      ▲                  │
            Audio Codes ── audio_codes┘                              Settings ─┘            Show Text
```

**How to use:**

- **Text-to-music (basic):** Fill in **caption** and **lyrics** in Gen Params, leave everything else default. Click Queue Prompt.
- **With reference audio:** Load an audio file in "Load Audio (refer audio)", connect it to Gen Params → `refer_audio`. This guides the style/timbre.
- **Cover mode:** Load the source song in "Load Audio (src audio)", connect it to either:
  - Gen Params → `src_audio` (sends raw audio directly), OR
  - audio2code Server → Audio Codes → Gen Params → `audio_codes` (converts to codes first)
  - Task type automatically switches to `cover` when `src_audio` or `audio_codes` is connected
  - **cover_strength** — noise injection strength (0 = clean cover, higher = more variation)
  - **remix_strength** — how much of the original to preserve (1.0 = full, 0 = none)
- **Repaint mode:** Connect source audio to Gen Params → `src_audio`, then check **is_repaint** in Gen Params. Set **repaint_start** and **repaint_end** (in seconds) to define the region to regenerate. Fill in **caption** and **lyrics** for the regenerated region.
- Cover/repaint mode automatically disables thinking, CoT caption, and CoT language — no LM is used.

**Settings tips:**

- **auto** toggle (ON by default): lets the LM decide bpm, key, duration, time signature. Turn OFF to set them manually.
- **thinking** = true: enables 5Hz LM audio code generation (higher quality, slower)
- **seed**: set a number for reproducible results, `-1` for random

### Workflow 2: Example Generate (LLM Auto-Generation)

**`workflows/example_generate.json`**

```
Example Generate Server ── gen_params ──► Text2music Server ──► Save Audio
        │                                        ▲                  │
        └── info ──► Show Text (LLM params)   Settings ─┘       Show Text (server info)
```

**How to use:**

1. Type a natural language description in **sample_query** (e.g. "upbeat pop song about summer")
2. Set **language** and **is_instrumental**
3. Click Queue Prompt — the LLM generates caption, lyrics, bpm, key, duration, etc., then synthesizes music
4. Check "LLM Generated Params" to see what the LLM produced

This is the equivalent of Gradio's "Simple mode" — fully automatic.

## Node Reference

### Server Nodes

These nodes call the ACE-Step API. Each has **mode** (cloud/local), **server_url**, and **api_key** fields.

| Node | Description | Outputs |
|------|-------------|---------|
| **audio2code Server** | Converts source audio → audio code tokens | `audio_codes`, `info` |
| **Example Generate Server** | LLM generates caption/lyrics/metadata from a query | `gen_params`, `caption`, `lyrics`, `info` |
| **Text2music Server** | Generates music (text2music/cover/remix/repaint) from gen_params + settings | `audio`, `info` |

### Parameter Nodes

| Node | Description | Key Fields |
|------|-------------|------------|
| **Text2music Gen Params** | Parameters for text2music / cover / remix / repaint | `caption`, `lyrics`, `vocal_language`, `bpm`, `key`, `duration`, `time_signature`, `auto`, `cover_strength`, `remix_strength`, `is_repaint`, `repaint_start`, `repaint_end` + optional `refer_audio`, `src_audio`, `audio_codes` |
| **Settings** | LM + DiT inference hyperparameters | `seed`, `thinking`, `use_cot_caption`, `use_cot_language`, `temperature`, `lm_cfg_scale`, `lm_top_p`, `lm_top_k`, `dit_guidance_scale`, `dit_inference_steps`, `dit_infer_method` |

### Utility Nodes

| Node | Description |
|------|-------------|
| **Audio Codes** | Editable passthrough for audio codes — paste manually or receive from audio2code Server. Displays received codes in the text area after execution. |
| **Show Text** | Displays any STRING input as multiline text with auto-sizing. |

### Built-in ComfyUI Nodes Used

- **LoadAudio** — load audio files from disk
- **SaveAudio** — save generated audio to disk

## Task Mode Summary

| Mode | Trigger | LM Used? | Key Parameters |
|------|---------|----------|----------------|
| **text2music** | No src_audio, no audio_codes, is_repaint OFF | Yes (if thinking=true) | caption, lyrics, bpm, key, duration |
| **cover** | src_audio connected OR audio_codes non-empty | No (auto-disabled) | cover_strength, remix_strength |
| **repaint** | src_audio connected AND is_repaint checked | No (auto-disabled) | repaint_start, repaint_end |
| **example generate** | Use Example Generate workflow | Yes (LLM generates params) | sample_query, language, is_instrumental |

## Tips

- **Cover/Repaint auto-safety:** When task is `cover` or `repaint`, `thinking`, `use_cot_caption`, `use_cot_language`, and `use_cot_metas` are all forced to `false` regardless of Settings values. The LM is not used for these tasks.
- **Auto metas:** When `auto` is ON in Gen Params, the `use_cot_metas` flag is sent as `true`, letting the LM infer bpm/key/duration/time_signature. When `auto` is OFF, your manual values are sent directly.
- **is_repaint toggle:** When OFF (default), `repaint_start` and `repaint_end` are hidden. When ON, they appear. Repaint requires `src_audio` to be connected.
- Workflows can be combined — users can copy nodes between workflows to create custom pipelines.
- Use **Show Text** nodes connected to `info` outputs to inspect generation parameters and server responses.

## License

[MIT](LICENSE)
