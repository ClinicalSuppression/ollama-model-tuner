# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- `scripts/local-preset.mjs` resolves the `local` preset for the current moment
  without writing anything.
- `scripts/local-preset-watch.mjs` keeps `presets.local` synced with the model
  loaded in Ollama, rewriting only that block and validating before an atomic
  write.
- `scripts/start-local-preset-watch.ps1` starts the watcher detached and
  idempotently, with `-Stop` for shutdown.
- README section documenting the oh-my-opencode-slim presets and the automatic
  `local` tracking.

### Fixed

- Derived preset models are fully qualified as `provider/model`.
- Indentation and trailing-comma handling preserve the rest of the config
  byte-identically across rewrites.

## 1.0.0

First stable release.

### Added

- `/tune` command that tunes exactly one installed Ollama model through mandatory
  popups for sampling, context length, and runtime/MTP/batch.
- No-argument `/tune` prints the full Ollama inventory and opens a picker of
  tunable models.
- `list-models.py` inventory of every running Ollama endpoint with model name,
  quant, max context, size, loaded state, and tunability.
- Model grouping that keeps an original and all of its tuned derivatives
  together, originals first, then derivatives by context size.
- Imatrix quant detection so `-i1-` and `imatrix` repos report `iQ4_K_M` and
  `iQ6_K` rather than the base quant.
- `tune-match.py` deterministic fuzzy matcher with exact-match, candidate, and
  no-match exit codes.
- `ollama-modelfile-tuner` skill: full Hugging Face chain research, comparison
  chart, explicit Best / Fastest recommendation, and derived-tag creation.
- `ollama-model-inventory` skill wrapping the endpoint scan.
- Derived tag naming rules that never collide with an original or an existing
  tuned tag.

### Safety

- Original model tags are never modified or deleted.
- Existing derived tags are never overwritten; collisions raise a question.
- Ollama server-wide settings are read only and reported as informational notes.
- Embedding-only models are listed but never tuned.

### Scope

- Ollama only. Other local serving stacks are not detected or tuned.