#!/usr/bin/env python3
"""
parse_address.py — decodifica o POI de entrega do 99 Food a partir do blob binario
do SharedPrefs com.didi.soda.address.manager.AddressStorage.xml.

O valor da chave <string name="Storage.Key"> e um base64 de uma serializacao
custom (Kotlin) com campos de tamanho-prefixado em UTF-16LE, intercalados com
ints (4 bytes LE) e doubles (8 bytes IEEE 754). Daqui extraimos:
  poiId, lat, lng, cityId, city, addressAll, neighborhood, county, countryCode

Uso:
  python parse_address.py <arquivo>   # arquivo = XML completo OU so o base64
Saida:
  JSON (stdout) com os campos do POI. Exit code != 0 se nao decodificar o minimo
  (poiId, lat, lng, cityId).
"""
import base64
import json
import re
import struct
import sys

# garante UTF-8 na saida (o addressAll tem acento; senao vira mojibake no Windows)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def extract_b64(text):
    """Pega o base64 de dentro do XML (ou devolve o proprio texto se ja for base64)."""
    m = re.search(r'<string name="Storage\.Key">(.+?)</string>', text, re.S)
    raw = m.group(1) if m else text
    return re.sub(r'\s|&#10;', '', raw.strip())


def walk_strings(b):
    """Percorre o blob extraindo tokens string tamanho-prefixado (UTF-16LE).

    Em cada offset le um int32-LE = n; se 1<=n<=300 e cabem n*2 bytes, tenta
    decodificar n chars UTF-16LE. Se for imprimivel (Latin), guarda e avanca
    4+n*2 bytes; senao avanca 1 byte.
    """
    tokens = []
    i = 0
    n = len(b)
    while i <= n - 4:
        ln = struct.unpack_from('<i', b, i)[0]
        if 1 <= ln <= 300 and i + 4 + ln * 2 <= n:
            chunk = b[i + 4:i + 4 + ln * 2]
            try:
                s = chunk.decode('utf-16-le')
            except Exception:
                s = None
            if s is not None and all(c == ' ' or c.isprintable() for c in s) \
               and not any(ord(c) < 32 for c in s):
                tokens.append((i, s))
                i += 4 + ln * 2
                continue
        i += 1
    return tokens


def scan_city_id(b):
    """Primeiro int32-LE no range de cityId BR do DiDi (~55.0xx.xxx)."""
    for i in range(0, len(b) - 4):
        v = struct.unpack_from('<i', b, i)[0]
        if 54_000_000 <= v <= 56_000_000:
            return v
    return None


def scan_coords(b):
    """Primeiro par de doubles (lat, lng) plausivel para o Brasil."""
    for i in range(0, len(b) - 16):
        lat = struct.unpack_from('<d', b, i)[0]
        lng = struct.unpack_from('<d', b, i + 8)[0]
        if -35 < lat < -3 and -75 < lng < -30:
            return round(lat, 7), round(lng, 7)
    return None, None


def classify(tokens):
    """Deriva os campos de endereco a partir dos tokens string."""
    strs = [s for _, s in tokens]

    poi_id = next((s for s in strs if re.fullmatch(r'\d{15,}', s)), '')

    country = next((s for s in strs if re.fullmatch(r'[A-Z]{2}', s)), '')

    # addressAll = token mais longo com " - " e um digito
    addr_cands = [s for s in strs if ' - ' in s and re.search(r'\d', s)]
    address_all = max(addr_cands, key=len) if addr_cands else ''

    city = neighborhood = county = ''
    if address_all:
        parts = [p.strip() for p in address_all.split(' - ')]
        if len(parts) >= 3:
            mid = parts[1]              # "Rio Branco, Porto Alegre"
            county = parts[-1]          # "RS"
            sub = [p.strip() for p in mid.split(',')]
            neighborhood = sub[0] if sub else ''
            city = sub[-1] if sub else ''
        elif len(parts) == 2:
            county = parts[-1]
            sub = [p.strip() for p in parts[0].split(',')]
            city = sub[-1] if sub else ''

    return {
        'poiId': poi_id,
        'city': city,
        'addressAll': address_all,
        'neighborhood': neighborhood,
        'county': county,
        'countryCode': country,
    }


def main():
    if len(sys.argv) < 2:
        print('uso: python parse_address.py <arquivo-xml-ou-base64>', file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1], encoding='utf-8', errors='replace') as f:
        text = f.read()

    try:
        blob = base64.b64decode(extract_b64(text))
    except Exception as e:
        print(f'erro decodificando base64: {e}', file=sys.stderr)
        sys.exit(1)

    tokens = walk_strings(blob)
    out = classify(tokens)
    out['cityId'] = scan_city_id(blob)
    lat, lng = scan_coords(blob)
    out['lat'] = lat
    out['lng'] = lng
    # placeholders para campos que a app retorna mas nao estao no AddressStorage
    out['countyGroupId'] = ''
    out['poiType'] = ''
    out['postalCode'] = ''

    # minimo viavel pra um evento coerente
    if not (out['poiId'] and out['cityId'] and out['lat'] is not None and out['lng'] is not None):
        print('decode incompleto: ' + json.dumps(out, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
