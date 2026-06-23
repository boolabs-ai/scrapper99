#!/usr/bin/env python3
"""
consolidate.py — junta as entidades do feed (heap_all.jsonl) num JSON de restaurantes.

Le:  <dir>/heap_all.jsonl  (uma HomeFeedEntity por linha, gerada por hook_feed.js)
Gera:
  <dir>/restaurantes.json       (limpo: shopId, nome, nota, avaliacoes, categoria, entrega_min, frete, ...)
  <dir>/restaurantes_full.json  (objeto cru de cada loja, todos os campos da API)

Dedup por shopId.
Uso: python consolidate.py <dir>
"""
import json, os, re, sys

d      = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
pt_lat = sys.argv[2] if len(sys.argv) > 2 else ''
pt_lng = sys.argv[3] if len(sys.argv) > 3 else ''
pt_cid = sys.argv[4] if len(sys.argv) > 4 else ''
shops_clean = {}
shops_full = {}

def rating_texts(rating):
    out = []
    try:
        s = json.dumps(rating, ensure_ascii=False)
        for m in re.finditer(r'\\?"text\\?"\s*:\s*\\?"([^"\\]+)', s):
            out.append(m.group(1))
    except Exception:
        pass
    return out

def parse_rating(rating):
    nota = av = cat = None
    for t in rating_texts(rating):
        t = t.strip()
        if re.match(r'^\d[.,]\d$', t) and nota is None:
            nota = t
        elif re.match(r'^\(.*\)$', t) and av is None:
            av = t.strip('()')
        elif not re.search(r'\d', t) and cat is None and len(t) > 2:
            cat = t
    return nota, av, cat

def add_shop(o):
    sid = o.get('shopId') or o.get('shop_id')
    if not sid or not (o.get('shopName') or o.get('name')):
        return
    key = str(sid)
    shops_full[key] = o
    nota, av, cat = parse_rating(o.get('rating'))
    dt = o.get('deliveryTime')
    pa = o.get('deliveryPriceAct')
    shops_clean[key] = {
        'shopId': key,
        'nome': o.get('shopName') or o.get('name'),
        'nota': nota,
        'avaliacoes': av,
        'categoria': cat,
        'entrega_min': round(dt / 60) if isinstance(dt, (int, float)) else None,
        'frete': 'Gratis' if pa == 0 else (f'R$ {pa/100:.2f}' if isinstance(pa, (int, float)) else None),
        'businessType': o.get('businessType'),
        'url': o.get('url'),
        'shopImg': o.get('shopImg'),
        'point_lat': pt_lat or None,
        'point_lng': pt_lng or None,
        'point_city_id': pt_cid or None,
    }

def walk(o):
    if isinstance(o, dict):
        if (o.get('shopId') or o.get('shop_id')) and (o.get('shopName') or o.get('name')):
            add_shop(o)
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)

jl = os.path.join(d, 'heap_all.jsonl')
if not os.path.exists(jl):
    print('ERRO: nao achei', jl)
    sys.exit(1)

for line in open(jl, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        walk(json.loads(line))
    except Exception:
        pass

clean = list(shops_clean.values())
full = list(shops_full.values())
json.dump(clean, open(os.path.join(d, 'restaurantes.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
json.dump(full, open(os.path.join(d, 'restaurantes_full.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('TOTAL restaurantes unicos (shopId):', len(clean))
print('  -> restaurantes.json      (limpo)')
print('  -> restaurantes_full.json (cru, todos os campos)')
for r in clean[:10]:
    print(('   %-45s nota %s (%s) | %s | %s min | %s'
           % (r['nome'][:45], r['nota'], r['avaliacoes'], r['categoria'], r['entrega_min'], r['frete'])
           ).encode('ascii', 'replace').decode())
