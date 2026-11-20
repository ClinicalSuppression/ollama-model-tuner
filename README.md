# ollama-model-tuner

OpenCode command, skills, and scripts for tuning local Ollama models with
creator-published Hugging Face settings, without ever modifying an original
model tag.

`/tune` lists every local Ollama endpoint and model, lets you pick one, researches
the full Hugging Face chain (quantizer, derivative, base model), and then asks you
for every setting through popups before creating a derived model.

## What it does

- Inventories running Ollama endpoints and groups models by base model, originals
  before tuned derivatives.
- Presents a comparison chart with max context, creator-published sampling
  presets, runtime/MTP recommendations, use case, suggested tag, and source.
- States an explicit Best / Fastest recommendation with VRAM fit for your GPU.
- Asks about sampling, context length, and runtime/MTP/batch as separate
  mandatory questions. Nothing is decided for you.
- Creates a new derived tag with `ollama create` and verifies the result.

It never overwrites an original model tag, never overwrites an existing derived
tag, and never changes Ollama server-wide settings.

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10/11 | Scripts use PowerShell paths and `C:\Users\...` locations |
| Python 3.8+ | Standard library only, no `pip install` needed |
| Ollama | A running `ollama serve` on `127.0.0.1:11434` or `OLLAMA_HOST` |
| OpenCode | Provides the `/tune` command and skill loading |

## Installation

### Terminal installation

```powershell
git clone https://github.com/ClinicalSuppression/ollama-model-tuner.git "$env:USERPROFILE\Documents\Visual Studio Projects\Projects\ollama-model-tuner"
Copy-Item -Recurse -Force "$env:USERPROFILE\Documents\Visual Studio Projects\Projects\ollama-model-tuner\commands\*" "$env:USERPROFILE\.config\opencode\commands\"
Copy-Item -Recurse -Force "$env:USERPROFILE\Documents\Visual Studio Projects\Projects\ollama-model-tuner\skills\*"   "$env:USERPROFILE\.config\opencode\skills\"
Copy-Item -Recurse -Force "$env:USERPROFILE\Documents\Visual Studio Projects\Projects\ollama-model-tuner\scripts\*"  "$env:USERPROFILE\.config\opencode\scripts\"
```

Restart OpenCode, then type `/tune`.

The scripts are referenced by absolute path
(`C:\Users\Chris\.config\opencode\scripts\...`), so either install to that
location or update the paths in `commands/tune.md` and the skill files.

### Manual installation

Copy the three folders into your OpenCode config directory
(`%USERPROFILE%\.config\opencode\`) as shown above. No `opencode.jsonc` change is
required; commands and skills are auto-discovered.

## Usage

```
/tune
```

Prints the endpoint summary and grouped model list, then opens a picker of
tunable models and runs the full tuner.

```
/tune ModelName
```

Resolves the name against installed Ollama models. Exact names proceed
immediately; anything else opens a confirmation popup with ranked candidates and
a `None of these` option. Nothing is auto-selected.

### The three mandatory questions

1. **Sampling** - one option per creator-published preset, plus keep existing,
   plus skip.
2. **Context** - default, 32K, 64K, 128K, 192K, max supported, or skip, each with
   an estimated VRAM total and remaining headroom.
3. **Runtime / MTP / batch** - Best/Fastest, fastest prefill, MTP with default
   batch, disable MTP, or keep existing.

A fourth question appears only when the computed derived tag already exists.

## Scripts

### `scripts/list-models.py`

Read-only Ollama inventory.

```powershell
python scripts\list-models.py             # aligned text table
python scripts\list-models.py --markdown  # Markdown table
python scripts\list-models.py --json      # machine readable
python scripts\list-models.py --tunable   # completion-capable models only
```

| Flag | Meaning |
|---|---|
| `--endpoint host:port` | Add an Ollama target (repeatable) |
| `--ports 12434` | Add ports to the default scan |
| `--timeout 1.5` | Per-request timeout in seconds (default 0.8) |
| `--tunable` | Keep only models whose capabilities include `completion` |

`OLLAMA_HOST` is scanned automatically; `OPENCODE_LOCAL_ENDPOINTS` adds extra
targets. Exit code `0` means models were found, `3` means no endpoint responded.

### `scripts/tune-match.py`

Deterministic fuzzy matcher. Prints JSON and exits `0` on an exact match, `1` when
candidates exist but none is exact, and `2` when nothing is plausible. It never
picks a model.

### `scripts/local-preset.mjs`

Prints the `local` preset resolved for the current moment, without writing
anything.

```powershell
node scripts\local-preset.mjs            # resolved preset as JSON
node scripts\local-preset.mjs --check    # exit 0 if a model resolves
node scripts\local-preset.mjs --dry-run  # explain the decision on stderr
```

It uses whatever model is resident in Ollama, choosing the most recently used
when several are loaded, and falls back to
`192k-TPK-tuned-Qwen3.8-9B-Dist-iQ4_K_M:latest` when nothing is loaded.

### `scripts/local-preset-watch.mjs` and `start-local-preset-watch.ps1`

Keeps the `local` preset in `oh-my-opencode-slim.json` in sync with Ollama
automatically. oh-my-opencode-slim exposes no command substitution inside preset
entries, so this watcher supplies the dynamic part: it polls Ollama and rewrites
only the `presets.local` block when the loaded model changes. With
`liveConfigRefresh` enabled (the default), the slim plugin then reloads the
config on its own.

```powershell
node scripts\local-preset-watch.mjs --once     # sync once and exit
node scripts\local-preset-watch.mjs            # sync, then poll every 15s
node scripts\local-preset-watch.mjs --dry-run  # report the decision only
```

Start it detached and idempotently with the launcher:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local-preset-watch.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-local-preset-watch.ps1 -Stop
```

Guarantees: only `presets.local` is touched, the rest of the file stays
byte-identical, the rewrite is validated with `JSON.parse` before an atomic
write, and an unchanged model produces no write at all.

| Variable | Meaning |
|---|---|
| `OLLAMA_HOST` | Ollama endpoint (default `127.0.0.1:11434`; a missing scheme is added) |
| `LOCAL_PRESET_CONFIG` | Config path override |
| `LOCAL_PRESET_INTERVAL` | Poll interval in ms (default 15000) |

## oh-my-opencode-slim presets

`oh-my-opencode-slim.json` holds one preset per active provider. Every provider
preset uses only models from that provider, with role-appropriate picks.

| Preset | Provider | Roles |
|---|---|---|
| `openai` | `openai` | `gpt-6-astra` orchestrates and reviews, `gpt-6-luna` explores, `gpt-6-sol` designs and fixes |
| `vertex` | `google-vertex` | `gemini-4-hydrogen` orchestrates, reviews, and designs; `gemini-3.5-flash-lite` explores; `gemini-3.5-flash` fixes |
| `nararouter` | `nararouter` | Claude Opus 5.5 orchestrates and reviews, DeepSeek V4.1 Flash explores, Claude Sonnet 5.5 designs, Kimi K2.7 Code fixes |
| `ollama` | `ollama` | 192k Defiant Fable `iQ6_K` for every role |
| `xollama` | `xollama` | Ternary Bonsai 2 27B for every role |
| `strata` | `strata` | `swift-iq2_xs` for every role |
| `local` | runtime | Tracks the model loaded in Ollama; falls back to the 192k Qwen3.8 Distill |

Model strings are fully qualified as `provider/model`. Switch presets with
`/preset <name>`.

### The `local` preset

`local` follows whatever Ollama has loaded. Because the slim schema has no
command substitution inside preset entries, the watcher in
`scripts/local-preset-watch.mjs` provides that behaviour: it rewrites only the
`presets.local` block when the loaded model changes, and `liveConfigRefresh`
picks the change up without a restart.

Start it once per session:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local-preset-watch.ps1
```

Without the watcher, `local` stays on whatever model was last written to the
file, so run `node scripts\local-preset-watch.mjs --once` after changing the
loaded model.

## Naming rules

Derived tags follow:

```
<Context>-<TPK-tuned if sampling/runtime changed>-<Abbreviated Name><-MTP>:<Quant>
```

Example, a 192K context build of
`hf.co/mradermacher/Qwen3.8-9B-Distill-uncensored-heretic-i1-GGUF:Q4_K_M` with
sampling and MTP enabled:

```
192k-TPK-tuned-Qwen3.8-9B-Dist-iQ4_K_M
```

Abbreviations save at least three characters: `unquantized` to `unq`,
`uncensored` to `unc`, `heretic` to `her`, `abliterated` to `abl`,
`instruct` to `inst`, `thinking` to `thk`. Imatrix quants take an `iQ` prefix.

## Safety rules

- Original model tags are never modified or deleted.
- Existing derived tags are never overwritten; a collision triggers a question.
- No sampling value, context length, or runtime parameter is inferred from
  conversation; every value comes from a popup answer.
- Ollama server-wide settings are read only and reported as notes.
- Embedding-only models are listed but never tuned.

## Skills

| Skill | Purpose |
|---|---|
| `skills/ollama-modelfile-tuner/SKILL.md` | Research, chart, recommend, and create derived models |
| `skills/ollama-model-inventory/SKILL.md` | Ollama endpoint and model inventory |

## Limitations

- Ollama only. LM Studio, vLLM, llama.cpp, KoboldCpp, and other stacks are out of
  scope.
- The `local` preset follows the loaded model only while the watcher is running;
  start it with `scripts\start-local-preset-watch.ps1`.
- Context-length and VRAM figures are estimates from model geometry and measured
  loads, not live measurements per tag.
- Non-thinking mode cannot be forced from a Modelfile; that requires the API's
  `enable_thinking: false`.
- Output length is a client-side setting and is not adjustable through the tuner.

## License

MIT