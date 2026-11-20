"""Inventory every local Ollama endpoint and its models.

Probes the default Ollama ports (plus any extra targets), collects model
metadata from /api/tags, /api/ps and /api/show, and prints the result grouped
by base model using the /tune naming rules (original first, then tuned
derivatives).

Read-only: it never loads, pulls, deletes, or modifies a model.

Usage:
  python list-models.py                # aligned text table
  python list-models.py --markdown     # Markdown table
  python list-models.py --json         # machine readable
  python list-models.py --tunable      # only completion-capable models
  python list-models.py --endpoint http://127.0.0.1:11434 --endpoint 12434
  python list-models.py --timeout 1.5

Environment:
  OLLAMA_HOST                Ollama host, same convention as the ollama CLI
  OPENCODE_LOCAL_ENDPOINTS   comma/space separated extra host:port entries
"""

import argparse
import concurrent.futures
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_PORTS = [11434, 12434, 11435]

VERSION_SUFFIX = re.compile(r'-v\d+$', re.I)
EMBED_HINTS = ('embed', 'nomic-bert', 'bge-', 'e5-', 'gte-', 'jina-')
ABBREVIATIONS = {
    'unq': 'unquantized',
    'abl': 'abliterated',
    'unc': 'uncensored',
    'bri': 'brilliance',
    'rsn': 'reasoning',
    'thk': 'thinking',
    'inst': 'instruct',
    'her': 'heretic',
    'deck': 'deckard',
}


def http_json(url, timeout, payload=None):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(4_000_000)
        if not body:
            return None
        return json.loads(body.decode('utf-8', 'replace'))


def normalize_base(entry):
    entry = str(entry).strip().rstrip('/')
    if not entry:
        return ''
    if entry.startswith(('http://', 'https://')):
        return entry
    if re.match(r'^\d+$', entry):
        return f'http://127.0.0.1:{entry}'
    return f'http://{entry}'


def host_from_env():
    raw = os.environ.get('OLLAMA_HOST', '').strip()
    if not raw:
        return ''
    raw = raw.replace('0.0.0.0', '127.0.0.1')
    return normalize_base(raw)


def looks_embedding(model):
    blob = ' '.join(
        str(model.get(key) or '') for key in ('name', 'family')
    ).lower()
    return any(hint in blob for hint in EMBED_HINTS)


def split_name(full):
    """Return (display repo name, quant, is_derived, context_token)."""
    name = str(full).strip()
    quant = ''
    if ':' in name:
        name, quant = name.rsplit(':', 1)
    if name.lower().startswith('hf.co/'):
        parts = name.split('/')
        if len(parts) >= 3:
            name = parts[-1]
    derived = False
    ctx = None
    match = re.match(r'^(\d+(?:\.\d+)?k|\d+ctx)-', name, re.I)
    if match:
        ctx = match.group(1).lower()
        name = name[match.end():]
        derived = True
    lowered = name.lower()
    if lowered.startswith('tpk-tuned-'):
        name = name[len('TPK-tuned-'):]
        derived = True
    elif lowered.startswith('tuned-'):
        name = name[len('tuned-'):]
        derived = True
    if name.lower().endswith('-mtp'):
        name = name[:-4]
        derived = True
    if VERSION_SUFFIX.search(name):
        name = VERSION_SUFFIX.sub('', name)
        derived = True
    return name, quant, derived, ctx


def canonical(text):
    """Normalise a name so originals and abbreviated tuned tags cluster."""
    value = str(text).lower()
    value = re.sub(r'hf\.co/[^/]+/', '', value)
    value = re.sub(r'-v\d+$', '', value)
    tokens = []
    for token in re.split(r'[^a-z0-9]+', value):
        if not token or token in ('i1', 'gguf', 'imatrix'):
            continue
        tokens.append(ABBREVIATIONS.get(token, token))
    return ''.join(tokens)


def ctx_tokens(token):
    if not token:
        return 0
    match = re.match(r'(\d+(?:\.\d+)?)k', token)
    if match:
        return int(float(match.group(1)) * 1024)
    match = re.match(r'(\d+)ctx', token)
    return int(match.group(1)) if match else 0


def collect_ollama(base, timeout):
    payload = http_json(base + '/api/tags', timeout)
    if not isinstance(payload, dict) or not isinstance(payload.get('models'), list):
        return None

    version = ''
    try:
        info = http_json(base + '/api/version', timeout)
        version = str((info or {}).get('version') or '')
    except Exception:
        pass

    loaded = set()
    try:
        running = http_json(base + '/api/ps', timeout)
        for item in (running or {}).get('models') or []:
            loaded.add(item.get('name') or item.get('model'))
    except Exception:
        pass

    models = []
    for item in payload['models']:
        name = item.get('name') or item.get('model')
        if not name:
            continue
        details = item.get('details') or {}
        model = {
            'name': name,
            'endpoint': base,
            'size_bytes': item.get('size') or 0,
            'modified_at': item.get('modified_at') or '',
            'quant': details.get('quantization_level') or '',
            'family': details.get('family') or '',
            'parameter_size': details.get('parameter_size') or '',
            'context': None,
            'loaded': name in loaded,
            'capabilities': [],
            'tunable': False,
        }
        try:
            info = http_json(base + '/api/show', timeout, payload={'model': name})
            caps = (info or {}).get('capabilities') or []
            model['capabilities'] = caps
            for key, value in ((info or {}).get('model_info') or {}).items():
                if key.endswith('.context_length') and isinstance(value, int):
                    model['context'] = max(model['context'] or 0, value)
            model['tunable'] = 'completion' in caps
        except Exception:
            model['tunable'] = not looks_embedding(model)
        models.append(model)

    return {
        'software': 'Ollama',
        'base': base,
        'version': version,
        'models': models,
    }


def probe(base, timeout):
    try:
        return collect_ollama(base, timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    except Exception:
        return None


# ------------------------------------------------------------------ grouping

def group_models(models):
    prepared = []
    for model in models:
        display, quant, derived, ctx = split_name(model['name'])
        item = dict(model)
        item['display'] = display
        item['derived'] = derived
        item['ctx_token'] = ctx
        item['quant'] = model.get('quant') or quant
        # A quant-looking tag suffix is more precise than the API's base quant
        # (for example :iQ4_K_M on a derived model).
        if re.match(r'^(?:i?q\d|iq\d|[ifb]p?\d)', quant or '', re.I):
            item['quant'] = quant
        blob = f"{model['name']} {display}".lower()
        embedded = re.search(r'(?:^|[-_.])(i?q\d(?:_[a-z]+)*|[ifb]p?\d+)$', display, re.I)
        if (
            item['quant']
            and ('-i1' in blob or 'imatrix' in blob
                 or quant.startswith('i')
                 or (embedded and embedded.group(1).lower().startswith('i')))
            and not item['quant'].lower().startswith(('i', 'iq'))
        ):
            item['quant'] = 'i' + item['quant']
        item['canonical'] = canonical(display)
        item['embedding'] = looks_embedding(model) or not model.get('tunable', False)
        prepared.append(item)

    groups = []
    for item in prepared:
        target = None
        for group in groups:
            if item['canonical'] == group['key']:
                target = group
                break
            ratio = difflib.SequenceMatcher(
                None, item['canonical'], group['key']
            ).ratio()
            if ratio >= 0.74:
                target = group
                break
        if target is None:
            groups.append({'key': item['canonical'], 'items': []})
            target = groups[-1]
        target['items'].append(item)

    for group in groups:
        originals = [i for i in group['items'] if not i['derived']]
        derived = [i for i in group['items'] if i['derived']]
        originals.sort(key=lambda i: i['name'].lower())
        derived.sort(key=lambda i: (ctx_tokens(i['ctx_token']), i['name'].lower()))
        group['items'] = originals + derived
        group['name'] = originals[0]['display'] if originals else derived[0]['display']
        group['chat'] = not all(i['embedding'] for i in group['items'])

    groups.sort(key=lambda g: (not g['chat'], g['name'].lower()))
    return groups


# ------------------------------------------------------------------- output

def human_size(size):
    if not size:
        return '-'
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.2f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return '-'


def human_ctx(value):
    if not value:
        return '-'
    value = int(value)
    if value % 1024 == 0:
        return f'{value // 1024}K'
    return str(value)


def markdown_table(models):
    lines = [
        '| # | Model | Kind | Endpoint | Quant | Max Ctx | Size | Modified | Tunable |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for index, model in enumerate(models, 1):
        kind = 'tuned' if model['derived'] else 'original'
        tunable = 'yes' if model.get('tunable') else 'no'
        modified = (model.get('modified_at') or '')[:19].replace('T', ' ')
        lines.append(
            '| {i} | `{name}` | {kind} | {endpoint} | {quant} | {ctx} | {size} | {mod} | {tun} |'.format(
                i=index,
                name=model['name'],
                kind=kind,
                endpoint=model.get('endpoint', ''),
                quant=model.get('quant') or '-',
                ctx=human_ctx(model.get('context')),
                size=human_size(model.get('size_bytes')),
                mod=modified or '-',
                tun=tunable,
            )
        )
    return '\n'.join(lines)


def human_table(servers, groups):
    out = ['OLLAMA ENDPOINTS']
    if not servers:
        out.append('  none responded')
    for server in servers:
        version = f" v{server['version']}" if server.get('version') else ''
        out.append(
            '  {software}{version:<10} {base:<30} {count} model(s)'.format(
                software=server['software'],
                version=version,
                base=server['base'],
                count=len(server['models']),
            )
        )
    out.append('')
    out.append('MODELS (grouped by base model: originals first, then tuned derivatives)')
    for group in groups:
        out.append('')
        out.append(f'[{group["name"]}]')
        for model in group['items']:
            flags = ['tuned' if model['derived'] else 'original']
            if model.get('loaded'):
                flags.append('loaded')
            if model.get('tunable'):
                flags.append('tunable')
            out.append(
                '  {name:<70} {quant:<10} {ctx:<6} {size:<10} {flags}'.format(
                    name=model['name'],
                    quant=(model.get('quant') or '-')[:10],
                    ctx=human_ctx(model.get('context')),
                    size=human_size(model.get('size_bytes')),
                    flags=','.join(flags),
                )
            )
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(
        description='Inventory local Ollama endpoints and models.'
    )
    parser.add_argument('--endpoint', action='append', default=[],
                        help='host:port or URL to probe (repeatable)')
    parser.add_argument('--ports', default='',
                        help='comma separated ports to add to the default scan')
    parser.add_argument('--timeout', type=float, default=0.8)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--markdown', action='store_true')
    parser.add_argument('--tunable', action='store_true',
                        help='only models with completion capability')
    args = parser.parse_args()

    bases = []
    env_host = host_from_env()
    if env_host:
        bases.append(env_host)
    for entry in args.endpoint:
        base = normalize_base(entry)
        if base:
            bases.append(base)
    for entry in re.split(r'[,\s]+', os.environ.get('OPENCODE_LOCAL_ENDPOINTS', '')):
        base = normalize_base(entry)
        if base:
            bases.append(base)
    ports = list(DEFAULT_PORTS)
    for entry in args.ports.split(','):
        if entry.strip().isdigit():
            ports.append(int(entry.strip()))
    for port in ports:
        bases.append(f'http://127.0.0.1:{port}')
    bases = list(dict.fromkeys(bases))

    servers = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(bases))) as pool:
        futures = {pool.submit(probe, base, args.timeout): base for base in bases}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                servers.append(result)
    servers.sort(key=lambda s: s['base'])

    models = [model for server in servers for model in server['models']]
    if args.tunable:
        models = [m for m in models if m.get('tunable')]
        kept = {m['endpoint'] for m in models}
        servers = [s for s in servers if s['base'] in kept]

    groups = group_models(models)
    flat = [model for group in groups for model in group['items']]

    if args.json:
        payload = {
            'scanned': len(bases),
            'endpoints': [
                {
                    'software': server['software'],
                    'version': server.get('version') or '',
                    'base': server['base'],
                    'models': len(server['models']),
                }
                for server in servers
            ],
            'total_models': len(flat),
            'groups': [
                {
                    'group': group['name'],
                    'models': [
                        {
                            'name': model['name'],
                            'kind': 'tuned' if model['derived'] else 'original',
                            'endpoint': model.get('endpoint'),
                            'quant': model.get('quant') or '',
                            'context': model.get('context'),
                            'size_bytes': model.get('size_bytes') or 0,
                            'modified_at': model.get('modified_at') or '',
                            'loaded': bool(model.get('loaded')),
                            'tunable': bool(model.get('tunable')),
                        }
                        for model in group['items']
                    ],
                }
                for group in groups
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0 if flat else 3

    if args.markdown:
        print(markdown_table(flat))
        return 0 if flat else 3

    print(human_table(servers, groups))
    if not flat:
        print('')
        print('No local Ollama endpoint responded on the scanned ports.')
        return 3
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    sys.exit(main())
