#!/usr/bin/env node
/**
 * Keep the `local` preset in sync with whatever model is loaded in Ollama.
 *
 * oh-my-opencode-slim's `liveConfigRefresh` watcher reloads the config when
 * oh-my-opencode-slim.json changes on disk, but it does not run commands inside
 * preset entries. This watcher closes that gap: it polls Ollama for the loaded
 * model and rewrites only the `local` preset block when the answer changes, so
 * the file stays static, valid JSON while the preset still tracks the runtime.
 *
 * Safety:
 *   - touches only presets.local
 *   - preserves key order, indentation, and comments-free formatting
 *   - writes atomically via temp file + rename
 *   - never loads, pulls, or unloads a model
 *
 * Usage:
 *   node local-preset-watch.mjs --once      # sync once and exit (for startup)
 *   node local-preset-watch.mjs             # sync, then watch until stopped
 *   node local-preset-watch.mjs --dry-run   # report the decision, write nothing
 *
 * Environment:
 *   OLLAMA_HOST           Ollama host (default 127.0.0.1:11434)
 *   LOCAL_PRESET_CONFIG   config file path override
 *   LOCAL_PRESET_INTERVAL poll interval in ms (default 15000)
 */

import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const DEFAULT_CONFIG = path.join(
  process.env.USERPROFILE || process.env.HOME || '.',
  '.config',
  'opencode',
  'oh-my-opencode-slim.json'
);
const CONFIG = process.env.LOCAL_PRESET_CONFIG || DEFAULT_CONFIG;
const FALLBACK = '192k-TPK-tuned-Qwen3.8-9B-Dist-iQ4_K_M:latest';
const INTERVAL = Number(process.env.LOCAL_PRESET_INTERVAL || 15000);
const ROLES = ['orchestrator', 'oracle', 'explorer', 'designer', 'fixer'];
const SKILLS_ALL = ['*'];
const SKILLS_REVIEW = ['simplify', 'requesting-code-review'];

const args = new Set(process.argv.slice(2));
const once = args.has('--once');
const dryRun = args.has('--dry-run');

function normalizeEndpoint(raw) {
  if (!raw) return 'http://127.0.0.1:11434';
  let host = raw.trim();
  if (!/^https?:\/\//i.test(host)) host = `http://${host}`;
  host = host.replace(/\/\/(0\.0\.0\.0|\[::\])(?=[:/]|$)/, '//127.0.0.1');
  return host.replace(/\/+$/, '');
}

const OLLAMA = normalizeEndpoint(process.env.OLLAMA_HOST);

function getJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 4000 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (c) => {
        body += c;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

async function resolveModel() {
  try {
    const data = await getJson(`${OLLAMA}/api/ps`);
    const live = (Array.isArray(data?.models) ? data.models : [])
      .filter((m) => typeof (m.name || m.model) === 'string' && (m.name || m.model))
      .map((m) => ({
        name: m.name || m.model,
        expires: Date.parse(m.expires_at || '') || 0,
      }));
    if (live.length === 0) return { model: FALLBACK, source: 'fallback' };
    live.sort((a, b) => b.expires - a.expires || a.name.localeCompare(b.name));
    return { model: live[0].name, source: 'loaded' };
  } catch {
    return { model: FALLBACK, source: 'fallback' };
  }
}

function qualified(model) {
  return model.startsWith('ollama/') ? model : `ollama/${model}`;
}

function localBlock(model) {
  const target = qualified(model);
  const block = {};
  for (const role of ROLES) {
    block[role] = {
      model: target,
      skills: role === 'orchestrator' ? SKILLS_ALL : role === 'oracle' ? SKILLS_REVIEW : [],
    };
  }
  return block;
}

/** Replace the presets.local block text while keeping the rest byte-identical. */
function buildText(original, model) {
  const presetsAt = original.search(/^[ \t]*"presets"\s*:\s*\{/m);
  if (presetsAt === -1) throw new Error('could not find top-level presets in config');
  const openBrace = original.indexOf('{', presetsAt);

  const braceAt = (start) => {
    let depth = 0;
    let inString = false;
    for (let i = start; i < original.length; i += 1) {
      const ch = original[i];
      if (inString) {
        if (ch === '\\') i += 1;
        else if (ch === '"') inString = false;
        continue;
      }
      if (ch === '"') inString = true;
      else if (ch === '{') depth += 1;
      else if (ch === '}') {
        depth -= 1;
        if (depth === 0) return i;
      }
    }
    return -1;
  };

  const presetsEnd = braceAt(openBrace);
  if (presetsEnd === -1) throw new Error('unbalanced presets block');

  const inner = original.slice(openBrace, presetsEnd);
  const localMatch = inner.match(/(\n[ \t]*"local"\s*:\s*\{)/);
  if (!localMatch) throw new Error('could not find presets.local in config');

  const localBrace = openBrace + localMatch.index + localMatch[0].indexOf('{');
  const localEnd = braceAt(localBrace);
  if (localEnd === -1) throw new Error('unbalanced presets.local block');

  // --- Verify our brace scan agrees with a real parser. ---
  const before = JSON.parse(original);
  const expected = before.presets.local;
  const probe = JSON.parse(
    `{"local":${original.slice(localBrace, localEnd + 1)}}`
  ).local;
  if (JSON.stringify(probe) !== JSON.stringify(expected)) {
    throw new Error('brace scan disagrees with parsed config; refusing to write');
  }

  // --- Confirm local is not the last preset, so the trailing comma is right.
  const remainder = original.slice(localEnd + 1, presetsEnd);
  const nextKey = remainder.match(/"([^"]+)"\s*:/);
  if (!nextKey) throw new Error('presets.local is the last key; comma handling unsupported');
  if (!/^\s*,/.test(remainder)) {
    throw new Error('expected a comma after presets.local');
  }

  // Derive child indent from the "local" key itself so repeated runs are
  // stable even if the block was rewritten with a different width before.
  // The capture includes the leading newline and the `"local": {` key itself.
  // Keep only the whitespace before the quote.
  const keyIndent = /\n([ \t]*)"/.exec(localMatch[1])?.[1] ?? '    ';
  // JSON.stringify with indent 2 already pads children by two spaces, so the
  // key indent alone puts children one level deeper, matching the file style.
  const rebuilt = JSON.stringify(localBlock(model), null, 2)
    .split('\n')
    .map((line, index) => (index === 0 ? line : keyIndent + line))
    .join('\n');

  const replaced =
    original.slice(0, localBrace) + rebuilt + original.slice(localEnd + 1);
  const priorModels = JSON.stringify(
    Object.fromEntries(
      Object.entries(expected).map(([role, spec]) => [role, spec.model ?? null])
    )
  );
  const nextModels = JSON.stringify(
    Object.fromEntries(
      Object.entries(localBlock(model)).map(([role, spec]) => [role, spec.model])
    )
  );
  return { text: replaced, changed: priorModels !== nextModels };
}

function writeAtomic(file, content) {
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, content, 'utf8');
  fs.renameSync(tmp, file);
}

async function sync() {
  const { model, source } = await resolveModel();
  const original = fs.readFileSync(CONFIG, 'utf8');
  const { text, changed } = buildText(original, model);

  if (dryRun) {
    console.log(`[watch] endpoint=${OLLAMA} source=${source} model=${qualified(model)}`);
    console.log(`[watch] would ${changed ? 'UPDATE' : 'leave unchanged'} ${CONFIG}`);
    return changed;
  }

  if (!changed) {
    console.log(`[watch] ${source}: ${qualified(model)} (no change)`);
    return false;
  }

  // Validate before writing so a bad rewrite can never land.
  JSON.parse(text);
  writeAtomic(CONFIG, text);
  console.log(`[watch] ${source}: updated local preset to ${qualified(model)}`);
  return true;
}

async function main() {
  await sync();
  if (once || dryRun) return 0;
  console.log(`[watch] watching every ${INTERVAL}ms (Ctrl+C to stop)`);
  setInterval(() => {
    sync().catch((err) => console.error(`[watch] error: ${err.message}`));
  }, INTERVAL);
  return new Promise(() => {});
}

main().catch((err) => {
  console.error(`[watch] fatal: ${err.message}`);
  process.exit(1);
});