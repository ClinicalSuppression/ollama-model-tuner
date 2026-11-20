---
description: Tune one local Ollama model with the full interactive tuner
---

# /tune

Tune exactly one installed Ollama model. The requested model is:

`$ARGUMENTS`

This command runs the `ollama-modelfile-tuner` skill in strict mode. Every
tuner decision must come from the user through the `question` tool. Do not
choose, assume, or apply anything on the user's behalf.

## Non-negotiable rules

1. Never select a model, sampling preset, context length, runtime setting, or
   output tag without an explicit answer from the user.
2. Never skip, merge, or auto-answer a tuner question, even when a value looks
   obvious, is already the recommended default, or was mentioned earlier in the
   conversation.
3. If any required question is unanswered or cancelled, stop. Do not write a
   Modelfile and do not run `ollama create`.
4. Never modify or delete the original model tag. Never overwrite an existing
   derived tag.
5. `ollama create` is the final step, only after every answer is collected.

## Step 1 - Resolve the model

### No argument: show the inventory and pick a model

If the argument above is empty, this command is the default local Ollama model
list:

1. Load the `ollama-model-inventory` skill with the `skill` tool.
2. Run:

```powershell
python C:\Users\Chris\.config\opencode\scripts\list-models.py --json
```

3. Print the endpoint summary (Ollama version, base URL, model count) and the
   full grouped model list as a Markdown table. Keep exact model names intact.
4. Build a `question` popup from the entries whose `tunable` value is `true`.
   One option per model, labelled with the exact model name, quant, and size.
   Put the endpoint and max context in the description. Add a `None / cancel`
   option. Do not preselect, recommend, or reorder by preference.
5. If no model is tunable, report that and stop.
6. Use the selected entry's exact `name` field as the confirmed model and
   continue to Step 2. Do not pass the label text through the fuzzy matcher
   again.

If the inventory script reports that no endpoint responded, report the scanned
ports and stop. Do not install, start, pull, or directly edit any Ollama model
to make the list appear.

### Argument supplied: match the name

Only Ollama models can be tuned. If the requested name belongs to another local
stack, report that this tool is Ollama-only and stop; do not substitute a
different model.

### Argument supplied: match the name

Run this, passing the argument text as a single quoted string (replace
`<argument text>` with the actual text the user typed):

```powershell
python C:\Users\Chris\.config\opencode\scripts\tune-match.py "<argument text>"
```

Interpret the JSON output and exit code:

- Exit `0` with `exact` set: the name matched exactly. State the resolved model
  and continue to Step 2. No confirmation popup is needed.
- Exit `1`: no exact match. Ask the user to confirm with a `question` popup.
- Exit `2`: no plausible match. Show the full inventory list and ask the user
  to choose or retype the name. Do not guess.
- Script error: report it and stop.

Confirmation popup requirements for a non-exact match:

- One option per candidate, labelled with the model name plus its quant and
  size.
- Put the match score and modified date in the option description.
- Always include a `None of these` option.
- Do not preselect, mark as recommended, or imply which candidate is correct.

If the user selects `None of these`, show the full inventory list and ask them
to pick from it or type the model name. Never fall back to the top-scoring
candidate.

## Step 2 - Check eligibility

Query `POST http://127.0.0.1:11434/api/show` for the confirmed model (use the
Ollama endpoint reported by the inventory when it is not the default port).
Require `capabilities` to include `completion`. If it does not, report that the
model is embedding-only or unsupported and stop. Do not create anything.

## Step 3 - Research and present the chart

Load the `ollama-modelfile-tuner` skill with the `skill` tool and follow its
research step. Follow the full Hugging Face chain (quantizer, derivative, base
model) and use only settings the creator actually published.

Print the complete comparison table with these columns:

`Model | Max Context | HF Sampling Settings | Best/Fastest Modelfile Runtime | Use Case | Suggested New Name | Source`

Also print the Best/Fastest recommendation, thinking and prompt quirks, and the
read-only server-only notes. If the creator lists no sampling recommendation,
write `None listed`. Never invent sampling values or context limits.

## Step 4 - Mandatory questions

Ask these in order. All are required for every run, even if the answer seems
obvious. Use the `question` tool for each.

### 4a. Sampling settings

Present every applicable option:

- One `Apply HF recommended (<use case>)` option per preset the creator
  publishes.
- `Keep existing sampling settings`.
- `Skip this model`.

If the creator publishes no preset, still ask, with `Keep existing sampling
settings` and `Skip this model`, and state that no preset was published.

### 4b. Context length

Present every applicable option for the confirmed model:

- `Keep model default (<current value>)`.
- `32K (32768)`, `64K (65536)`, `128K (131072)`, `192K (196608)` where each is
  within the model's maximum.
- `Max supported (<maximum>)`.
- `Skip this model`.

Include the estimated VRAM total and remaining headroom in each description.

### 4c. Runtime, MTP, and batch

Present every applicable option:

- `Apply Best/Fastest runtime (draft_num_predict 2, num_batch ...)`, with the
  exact values in the label and description.
- `Disable MTP (draft_num_predict 0)` when the model has embedded MTP.
- `Keep existing runtime settings`.

Do not apply any runtime value before the user answers.

### 4d. Output tag (only when the computed tag already exists)

Compute the derived name using the skill's naming rules. If that exact tag is
already in `ollama list`, ask:

- `Create as <computed-tag>-v2`.
- `Abort`.

The user may type a different name as a custom answer. Never overwrite an
existing tag and never silently pick a suffix.

## Step 5 - Create and verify

Proceed only after 4a, 4b, and 4c are answered, plus 4d when it was shown.

1. Export the original Modelfile with `ollama show --modelfile <original>`.
2. Remove existing `PARAMETER` lines for keys being overridden, while keeping
   `FROM`, `TEMPLATE`, `SYSTEM`, stop parameters, and unrelated parameters.
3. Append the confirmed `PARAMETER` lines and write a temp Modelfile under
   `C:\Users\Chris\AppData\Local\Temp\opencode`.
4. Run `ollama create <new-tag> -f <temp-modelfile>`.
5. Verify with `ollama show <new-tag>` and `ollama list`, confirming the
   original tag still exists unchanged.

## Step 6 - Report

Report the source model, confirmed settings, new tag, measured or estimated
VRAM use, and the selection string. List any step the user skipped.

## Pre-create checklist

Before running `ollama create`, verify:

- [ ] Model resolved, and any non-exact match confirmed by the user.
- [ ] Sampling question answered.
- [ ] Context question answered.
- [ ] Runtime question answered.
- [ ] Tag collision question answered, if applicable.

If any box is unchecked, ask the missing question now. Never proceed silently.
