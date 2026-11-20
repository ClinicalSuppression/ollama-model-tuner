"""Fuzzy model matcher for the /tune command.

Reads installed Ollama models, ranks them against a free-text query, and
prints JSON. It never selects a model: the caller must confirm any non-exact
match with the user. Read-only and stdlib only.

Exit codes:
  0  exact match found (case-insensitive, full name including tag)
  1  candidates found, none exact
  2  no plausible candidate
"""

import difflib
import json
import re
import subprocess
import sys
import urllib.request

OLLAMA_TAGS = 'http://127.0.0.1:11434/api/tags'
MIN_SCORE = 0.45
MAX_CANDIDATES = 5


def normalize(value):
    text = str(value).lower()
    text = re.sub(r'^hf\.co/[^/]+/', '', text)
    return re.sub(r'[^a-z0-9]+', '', text)


def fetch_models():
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        models = []
        for item in data.get('models') or []:
            details = item.get('details') or {}
            models.append({
                'name': item.get('name') or item.get('model'),
                'size': item.get('size') or 0,
                'modified_at': item.get('modified_at') or '',
                'quant': details.get('quantization_level') or '',
                'family': details.get('family') or '',
            })
        return models, 'api'
    except Exception:
        pass

    result = subprocess.run(
        'ollama list', shell=True, capture_output=True, text=True, encoding='utf-8'
    )
    models = []
    for line in (result.stdout or '').splitlines()[1:]:
        parts = re.split(r'\s{2,}', line.strip())
        if parts and parts[0]:
            models.append({
                'name': parts[0],
                'size': 0,
                'modified_at': ' '.join(parts[3:]) if len(parts) > 3 else '',
                'quant': '',
                'family': '',
            })
    return models, 'cli'


def variants(name):
    text = str(name).lower()
    tail = text.split('/')[-1]
    base = tail.split(':')[0]
    return [normalize(text), normalize(tail), normalize(base)]


def score(query, name, tokens):
    query_norm = normalize(query)
    candidates = [value for value in variants(name) if value]
    if not candidates:
        return 0.0

    best = 0.0
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, query_norm, candidate).ratio()
        if query_norm and query_norm in candidate:
            ratio += 0.15
        elif candidate in query_norm:
            ratio += 0.10
        best = max(best, ratio)

    if tokens:
        hits = sum(1 for token in tokens if token and any(token in c for c in candidates))
        best += 0.25 * (hits / len(tokens))
    return min(1.0, round(best, 4))


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(json.dumps({'error': 'missing model query'}, indent=2))
        return 2

    query = ' '.join(sys.argv[1:]).strip()
    models, source = fetch_models()
    if not models:
        print(json.dumps({'query': query, 'error': 'no installed models found'}, indent=2))
        return 2

    exact = None
    for model in models:
        if str(model['name']).lower() == query.lower():
            exact = model['name']
            break

    tokens = [normalize(part) for part in re.split(r'\s+', query) if part.strip()]
    ranked = []
    for model in models:
        value = score(query, model['name'], tokens)
        ranked.append({
            'name': model['name'],
            'score': value,
            'size_gb': round((model['size'] or 0) / 1_000_000_000, 2),
            'modified_at': model['modified_at'],
            'quant': model['quant'],
            'family': model['family'],
        })
    ranked.sort(key=lambda item: (-item['score'], item['name']))

    payload = {
        'query': query,
        'source': source,
        'installed': len(models),
        'exact': exact,
        'candidates': ranked[:MAX_CANDIDATES],
    }
    print(json.dumps(payload, indent=2))

    if exact:
        return 0
    if ranked and ranked[0]['score'] >= MIN_SCORE:
        return 1
    return 2


if __name__ == '__main__':
    sys.exit(main())
