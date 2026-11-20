#!/usr/bin/env node
/**
 * Local preset resolver for oh-my-opencode-slim.
 *
 * Picks the model that is currently loaded in Ollama and assigns it to every
 * agent role. If nothing is loaded, falls back to the 192k Qwen3.8 Distill
 * build. Never invents a model, never loads or unloads anything.
 *
 * Usage:
 *   node local-preset.mjs            # print the resolved preset (JSON)
 *   node local-preset.mjs --check    # exit 0 if a model resolves, 2 if not
 *   node local-preset.mjs --dry-run  # explain the decision on stderr
 *
 * Exit codes: 0 resolved, 2 no usable model (Ollama unreachable and no
 * registered fallback), 1 unexpected error.
 */

import http from 'node:http';

function normalizeEndpoint(raw) {
  if (!raw) return 'http://127.0.0.1:11434';
  let host = raw.trim();
  if (!/^https?:\/\//i.test(host)) {
    host = `http://${host}`;
  }
  // Ollama's CLI convention allows 0.0.0.0:port to mean "listen everywhere";
  // for client calls 127.0.0.1 is the right target.
  host = host.replace(/\/\/(0\.0\.0\.0|\[::\])(?=[:/]|$)/, '//127.0.0.1');
  return host.replace(/\/+$/, '');
}

const OLLAMA = normalizeEndpoint(process.env.OLLAMA_HOST);

const FALLBACK = '192k-TPK-tuned-Qwen3.8-9B-Dist-iQ4_K_M:latest';

const SKILLS_ALL = ['*'];
const SKILLS_REVIEW = ['simplify', 'requesting-code-review'];
const ROLES = ['orchestrator', 'oracle', 'explorer', 'designer', 'fixer'];

const args = new Set(process.argv.slice(2));
const checkOnly = args.has('--check');
const dryRun = args.has('--dry-run');

function getJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 4000 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('timeout', () => {
      req.destroy(new Error('timeout'));
    });
    req.on('error', reject);
  });
}

async function loadedModel() {
  try {
    const data = await getJson(`${OLLAMA}/api/ps`);
    const models = Array.isArray(data?.models) ? data.models : [];
    const live = models
      .filter((m) => typeof (m.name || m.model) === 'string' && (m.name || m.model).length > 0)
      .map((m) => ({
        name: m.name || m.model,
        // Ollama refreshes expiry on every request, so the model with the
        // furthest expiry is the one used most recently.
        expires: Date.parse(m.expires_at || '') || 0,
      }));
    if (live.length === 0) return null;
    live.sort((a, b) => b.expires - a.expires || a.name.localeCompare(b.name));
    if (dryRun && live.length > 1) {
      console.error(`[local-preset] ${live.length} models resident: ${live.map((m) => m.name).join(', ')}`);
    }
    return live[0].name;
  } catch (err) {
    if (dryRun) {
      console.error(`[local-preset] /api/ps unavailable: ${err.message}`);
    }
    return null;
  }
}

function presetFor(model) {
  // Only prefix when the string is not already qualified. Ollama model names
  // can contain slashes (hf.co/owner/repo:tag), so check known provider ids
  // rather than looking for a slash.
  const qualified = model.startsWith('ollama/') ? model : `ollama/${model}`;
  const block = {};
  for (const role of ROLES) {
    block[role] = {
      model: qualified,
      skills: role === 'orchestrator' ? SKILLS_ALL : role === 'oracle' ? SKILLS_REVIEW : [],
    };
  }
  return block;
}

async function main() {
  const live = await loadedModel();
  const model = live || FALLBACK;
  const source = live ? 'loaded' : 'fallback';

  if (dryRun) {
    console.error(`[local-preset] endpoint=${OLLAMA}`);
    console.error(`[local-preset] loaded=${live || 'none'}`);
    console.error(`[local-preset] using=${model} (${source})`);
  }

  if (checkOnly) {
    if (dryRun) {
      console.error(`[local-preset] ok (${source})`);
    }
    return 0;
  }

  const output = {
    preset: 'local',
    presets: { local: presetFor(model) },
    resolved: { model, source, endpoint: OLLAMA },
  };
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(`[local-preset] error: ${err.message}`);
    process.exit(1);
  });