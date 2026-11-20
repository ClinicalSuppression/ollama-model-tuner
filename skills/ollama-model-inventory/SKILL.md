---
name: ollama-model-inventory
description: "Inventory every local Ollama endpoint and list its models, grouped by base model with originals before tuned derivatives, sorted by the /tune naming rules. Use when asked to list local Ollama models, list installed models, show what Ollama is serving, or as the default model picker for /tune. Ollama only: never query or tune LM Studio, vLLM, llama.cpp, KoboldCpp, or other stacks."
---

# Ollama Model Inventory

Detect every running local Ollama endpoint, collect model metadata, and print
one logically sorted list. This skill supports Ollama only.

The inventory is read-only. It never loads, pulls, deletes, or modifies a
model.

## Script

`C:\Users\Chris\.config\opencode\scripts\list-models.py`

```powershell
python C:\Users\Chris\.config\opencode\scripts\list-models.py             # aligned text table
python C:\Users\Chris\.config\opencode\scripts\list-models.py --markdown  # Markdown table
python C:\Users\Chris\.config\opencode\scripts\list-models.py --json      # JSON for parsing
python C:\Users\Chris\.config\opencode\scripts\list-models.py --tunable  # completion-capable only
```

Options:

| Flag | Meaning |
|---|---|
| `--endpoint host:port` | Add an Ollama target (repeatable) |
| `--ports 12434` | Add ports to the default scan |
| `--timeout 1.5` | Per-request timeout in seconds (default 0.8) |
| `--tunable` | Keep only models whose capabilities include `completion` |
| `--json` / `--markdown` | Output format |

Environment:

- `OLLAMA_HOST` follows the same convention as the `ollama` CLI and is scanned
  automatically.
- `OPENCODE_LOCAL_ENDPOINTS` adds extra targets, comma- or space-separated.

Exit codes: `0` models found, `3` no endpoint responded.

## Detection

An endpoint is Ollama when `GET /api/tags` returns a JSON object with a
`models` array. Version comes from `GET /api/version`, loaded state from
`GET /api/ps`, and per-model detail from `POST /api/show` with
`{"model": "<name>"}`.

Default ports: 11434, 12434, 11435. Only running endpoints appear; a stopped
Ollama instance is not detected.

## Metadata

Per model: exact name, size, modified date, family, parameter size, quant,
loaded state, capabilities, and max context (the largest
`*.context_length` value in `/api/show` `model_info`).

`tunable` is `true` only when `capabilities` contains `completion`. Embedding
models such as `nomic-embed-text` are listed but never tunable.

## Sorting rules

Sorting follows the `ollama-modelfile-tuner` naming convention so an original
and every tuned derivative of it stay together.

1. **Parse the name.** Split `:quant`, strip `hf.co/<owner>/`, then detect the
   derived prefix `<context>-`, the `TPK-tuned-` marker, the `-MTP` marker, a
   trailing `-vN` revision, and a quant-looking tag suffix.
2. **Group.** Canonicalise names (lowercase, strip separators, expand the tuner
   abbreviations `unq`, `abl`, `unc`, `bri`, `rsn`, `thk`, `inst`, `her`,
   `deck`) and cluster by equality or `difflib` ratio `>= 0.74`.
3. **Order inside a group.** Originals first, then tuned derivatives by context
   size ascending, then name.
4. **Order groups.** Chat groups before embedding-only groups, then by name.
5. **Quant label.** Prefer a quant-looking tag suffix (`:iQ4_K_M`), otherwise
   the API value. Apply the imatrix prefix when the name contains `-i1` or
   `imatrix` and the quant does not already start with `i`.

## Presenting the inventory

- Show the endpoint summary first (software, version, base URL, model count).
- Then show the grouped list with full model names, quant, max context, size,
  and flags (`original`, `tuned`, `loaded`, `tunable`).
- Use `--markdown` when the output is going into chat.
- Keep exact model names intact; they are the strings the user will type into
  `/tune`.
- Never add or infer models that the API did not return.

## Failure handling

- If nothing responds, report the scanned ports and suggest `--endpoint` or a
  longer `--timeout`, then stop.
- If an endpoint answers but returns malformed JSON, skip it.
- Never install, start, stop, pull, or delete anything to make the inventory
  succeed.
