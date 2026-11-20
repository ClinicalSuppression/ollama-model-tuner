---
name: ollama-modelfile-tuner
description: "Research Hugging Face sampling, context, and runtime/MTP recommendations for local Ollama models, check hardware VRAM fit, recommend the best/fastest per-model settings, confirm changes via interactive popups, and create derived Ollama Modelfiles without overwriting originals or modifying Ollama globally."
---

# Ollama Modelfile Tuner

Use this skill whenever the user asks to inspect, tune, or update Ollama Modelfiles (one model, several models, or all local models) using creator-recommended Hugging Face settings, custom context lengths, and optimal per-model runtime parameters (MTP, batch size, offload).

## Rules

- **Never overwrite an original model tag.** Always create a new derived local model using `ollama create <new-name> -f <temp-modelfile>`.
- **Model-only changes (never modify Ollama globally).** Apply changes strictly to derived Modelfiles. Never change Ollama server-wide environment variables, system/user env, or global server config. Read active server env (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_CONTEXT_LENGTH`) **read-only** for VRAM math, and surface any server-only bottleneck as an informational note only.
- **Always recommend what is Best / Fastest.** Every comparison output must include an explicit **Best / Fastest Recommendation** per model (and an overall pick when tuning multiple models), grounded in the model's quant/MTP traits and local GPU VRAM.
- **Skip embedding-only models** automatically (any model whose `/api/show` `capabilities` lack `"completion"`, such as `nomic-embed-text:latest`).
- **Never invent sampling parameters or context limits.** If Hugging Face lists no sampling recommendations, report `"None listed"` and do not fabricate defaults.
- **Full-chain Hugging Face lookup:** Quantizer repos (`mradermacher`, `bartowski`, `DavidAU`, `unsloth`, etc.) frequently omit sampling parameters and link to an upstream abliterated/fine-tuned repo, which in turn links to the original base model. Always follow the full upstream chain (quantizer -> derivative -> original base model) until you have verified all sampling presets, context limits, MTP notes, and quirks.

## Step 1: Inventory local Ollama models & hardware

1. Run `ollama list` to get exact installed model names. For a full inventory
   across every local endpoint, load the `local-model-inventory` skill instead;
   only Ollama models with `completion` capability are tunable.
2. Collect a **read-only hardware & Ollama server snapshot**:
   - GPU VRAM & backend (e.g., `Win32_VideoController` / `nvidia-smi` / `%LOCALAPPDATA%\Ollama\server.log` `inference compute` line).
   - Active server-only settings from `%LOCALAPPDATA%\Ollama\server.log` (`server config` line) or process env: `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_CONTEXT_LENGTH`.
3. Query Ollama `/api/show` (or `ollama show --modelfile` + `ollama show`) for each candidate:
   - `capabilities`: skip if `"completion"` is missing (embedding-only models).
   - `parameters`: record any currently set sampling (`temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `presence_penalty`, `stop`) and runtime (`num_ctx`, `draft_num_predict`, `num_batch`, `num_gpu`, `use_mmap`, `num_thread`) values.
   - `model_info`: extract max-supported context length from any `*.context_length` integer field, plus attention/KV geometry (`*.block_count`, `*.attention.head_count_kv`, `*.attention.key_length`).
   - **Embedded MTP detection:** check `model_info` for `*.nextn_predict_layers > 0`, or check tensors / HF repo files for `blk.*.nextn.*` or `mtp.` tensors (remember: Ollama defaults `draft_num_predict` to `0`/off for embedded MTP GGUFs unless explicitly set in the Modelfile).
   - Quant & imatrix detection: extract the quant from the `:TAG` (e.g., `Q4_K_M`, `IQ4_XS`, `Q6_K`). If the repo name or filename contains `-i1-` or `imatrix` (case-insensitive) and the quant does not already start with `I`/`i`, prefix it with `i` (e.g., `Q4_K_M` -> `iQ4_K_M`, `Q6_K` -> `iQ6_K`; `IQ4_XS` -> `IQ4_XS`).
4. **If the user did NOT specify which models to tune** (nor explicitly say "all"):
   - Show a `question` popup (`multiple: true` or `All chat models` + each eligible chat model) to let them pick which model(s) to research and chart.
   - If the user *already* named specific model(s) or said "all", skip this initial popup.

## Step 2: Hugging Face research

For each eligible chat model:
1. If the name starts with `hf.co/<owner>/<repo>`, fetch `https://huggingface.co/<owner>/<repo>` (and `?blobs=true` / `raw/main/README.md` via `webfetch`). Otherwise use `websearch` (`site:huggingface.co <model>`), falling back to `webfetch` on `https://huggingface.co/api/models?search=<query>&limit=15` if `websearch` returns no results.
2. Look for:
   - Sampling presets (`temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `presence_penalty`) and their **use cases** (e.g., General, Coding, Reasoning/Thinking, Creative).
   - **MTP / speculative decoding guidance:** draft acceptance rates, recommended `draft_num_predict` (`2` vs `4`), and warnings where MTP hurts or adds ~0% gain (e.g. `IQ1_M`, `IQ1_S`, `PTQ1_0`, or creative runs with `temperature > 1.0`).
   - **Runtime / context quirks:** minimum recommended context, `num_batch` notes, Flash Attention compatibility issues, KV-cache sensitivity, and thinking-mode controls (`<|think|>`, `/think` vs `/no_think`, `{REASON:...}`, effort levels).
   - Max-supported context length (cross-check against `model_info.*.context_length`).
3. If the quantizer page links to an upstream base model and does not itself list complete sampling/runtime presets, fetch the upstream base model page as well.

## Step 3: Naming rules (non-destructive derived tag)

Format:
`<Context>-<TPK-tuned if sampling/runtime changed>-<Abbreviated Name><-MTP if draft_num_predict enabled & not in name>:<Quant>`

- **Context prefix:** e.g., `32k`, `64k`, `128k`, `256k` (use the chosen `num_ctx`, or the model's active/default context if unchanged; if `num_ctx` is not an exact `k` multiple, use e.g. `48k` or `<N>ctx`).
- **Settings marker:** Include `TPK-tuned` if sampling (`temperature`, `top_p`, `top_k`, etc.) or runtime (`draft_num_predict`, `num_batch`, etc.) parameters are changed; omit it if only context is changed.
- **MTP marker:** Append `-MTP` before `:<Quant>` if `draft_num_predict > 0` is newly enabled and `MTP` is not already in `<Abbreviated Name>`.
- **Model name:** Strip `hf.co/<owner>/` and `:TAG`, keep the full family/version name distinguishable, and apply **only** abbreviations that save **at least 3 characters**:
  - `unquantized` -> `unq`
  - `abliterated` -> `abl`
  - `uncensored` -> `unc`
  - `Brilliance` -> `Bri`
  - `Reasoning` -> `Rsn`
  - `Thinking` -> `Thk`
  - `Instruct` -> `Inst`
  - `heretic` / `Heretic` -> `her` / `Her`
  - `The-DECKARD` / `DECKARD` -> `Deck`
  - `-GGUF` -> *(omit)*
  - `-i1` -> *(omit; represented by `iQ` in quant)*
- **Quant suffix:** `:<Quant>` with `iQ` for imatrix quants (e.g., `:Q4_K_M`, `:iQ4_K_M`, `:iQ6_K`, `:iQ4_XS`, `:IQ2_XS`).

## Step 4: Present the comparison chart & Best/Fastest recommendation

Before showing any popups, print a Markdown table covering every eligible model requested:

`| Model | Max Context | HF Sampling Settings | Best/Fastest Modelfile Runtime | Use Case | Suggested New Name | Source |`

- If a model has **multiple** recommended presets/use cases, give each preset its own row.
- **Runtime / MTP recommendation rules (per-model Modelfile `PARAMETER`s only):**
  - **MTP (`draft_num_predict`):**
    - Embedded MTP present at `IQ2_XXS`/`Q2_K` or higher & `temp <= 1.0`: recommend **`draft_num_predict 2`** (or `4` when HF card recommends 4; `2` is the reliable sweet spot on 16 GB consumer GPUs) — gives ~30–100% decode speedup.
    - `IQ1_M` / `IQ1_S` / `PTQ1_0` or high-temp creative runs (`temp > 1.0`): recommend **disabling MTP (`draft_num_predict 0` or omit)** because low acceptance slows decode.
    - No MTP tensors: report `No MTP`.
  - **Batch (`num_batch`):** Ollama reserves `+768 MiB` for `num_batch >= 1024` and `+2 GiB` for `num_batch >= 2048`. Recommend `num_batch 512` (default) when VRAM headroom is tight (`< 3 GiB`), or `num_batch 1024`/`2048` for faster prompt prefill when >= 3 GiB VRAM remains free at the target `num_ctx`.
  - **Offload (`num_gpu` / `use_mmap`):** Leave auto unless a full offload requires pinning or avoiding mmap.
- **Below the table, always include:**
  1. **Best / Fastest Recommendation:** Explicitly state the best/fastest configuration per model (and overall pick if tuning multiple models), with expected VRAM fit and speed/quality trade-off.
  2. **Thinking & prompt quirks** (e.g., `<|think|>`, `{REASON:...}`, effort defaults).
  3. **Server-only notes (read-only, informational — never auto-applied):** Note whether the user's current Ollama env (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_NUM_PARALLEL`) is already optimal or if a chosen `num_ctx` would exceed VRAM without a server-side `OLLAMA_KV_CACHE_TYPE=q8_0`.

## Step 5: Interactive `question` popups

1. **Popup 1 — Scope** *(skip if user only asked about 1 model)*:
   - `Change all models`
   - `Change one model` *(if chosen, follow up with a `question` listing the models)*
   - *(Built-in "Type your own answer" allows choosing a custom subset.)*

2. **Popup 2 — Sampling settings:**
   - For the selected model(s), ask whether to change sampling settings and which preset to apply if multiple exist (e.g., `Apply HF recommended (<use case>)`, `Keep existing settings`, `Skip this model`). If multiple selected models have different presets, include one question per model.

3. **Popup 3 — Context length (per-model):**
   - Ask **individually per selected model**, showing that model's exact max-supported context and VRAM fit note. Include applicable choices up to the model's max context:
     - `Keep model default`
     - `32K (32768)`
     - `64K (65536)`
     - `128K (131072)` *(when `max_context >= 131072`)*
     - `192K (196608)` *(when `max_context >= 196608`)*
     - `Max supported (<max>)`
     - `Skip this model`
     - Plus built-in custom text; parse shorthand like `128k`/`128K` -> `131072`, `192k` -> `196608`, `48k` -> `49152`, or raw integers.
   - If more than 4 models are selected at once, first offer `Set each model individually` vs `Apply one shared context cap` so the popup stays manageable.

4. **Popup 4 — Runtime / MTP / Batch (per-model):**
   - For each selected model, confirm the per-model runtime `PARAMETER`s (show the Best/Fastest pick first with `(Recommended)`):
     - `Apply Best/Fastest runtime (e.g. draft_num_predict 2, num_batch ...) (Recommended)`
     - `Disable MTP (draft_num_predict 0)` *(shown when embedded MTP is present)*
     - `Keep existing runtime settings`
   - Never show a popup for Ollama server-wide env vars.

## Step 6: Create derived Modelfiles & verify

For each confirmed model:
1. Export the original Modelfile: `ollama show --modelfile <original-model>`.
2. Remove any existing `PARAMETER` lines for keys being overridden (`temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `presence_penalty`, `num_ctx`, `draft_num_predict`, `num_batch`, `num_gpu`, `use_mmap`, `num_thread`) while preserving `FROM` (pointing to the original model or its base blob), `TEMPLATE`, `SYSTEM`, `stop` parameters, and unrelated parameters.
3. Append the chosen `PARAMETER` lines.
4. Write to a temp Modelfile (e.g., under `C:\Users\Chris\AppData\Local\Temp\opencode`) and run:
   `ollama create <new-name> -f <temp-modelfile>`
5. Verify with `ollama show <new-name>` (confirming all new `PARAMETER`s, including `draft_num_predict` / `num_batch` / `num_ctx`) and `ollama list` (confirming both the original and new derived model exist).
