"""
schools.py — coletor de escolas (OpenStreetMap/Overpass) -> fila do crawler 99.

Dada uma área (ponto + raio em km), consulta o Overpass por `amenity=school` e grava as
coordenadas das escolas no arquivo de fila (`crawler/queue.txt`, formato `lat,lng,nome`)
que o `crawl_99.py --queue` consome. Self-contained: usa só o OSM (mesmo ecossistema que o
signer4 usa via Nominatim), sem depender do 99/proxy/assinatura.

Uso:
  python -m crawler.schools --point "-16.6869,-49.2648" --radius 3
  python -m crawler.schools --point "-16.69,-49.26" --radius 5 --out crawler/queue.txt --append
  python -m crawler.schools --point "-16.69,-49.26" --types school,college,kindergarten

Depois (passo separado), bater cada escola com o crawler on-device:
  python -m crawler.crawl_99 --queue crawler/queue.txt --delay 60 --resume
"""
import argparse
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "queue.txt"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
LAT_KM = 111.32  # 1° de latitude ≈ 111.32 km (igual configs/cities.py)


def _haversine_m(a, b):
    """Distância aproximada em metros entre (lat,lng) a e b."""
    (la1, lo1), (la2, lo2) = a, b
    dlat = (la2 - la1) * LAT_KM * 1000
    dlng = (lo2 - lo1) * LAT_KM * 1000 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dlat, dlng)


def _build_query(lat, lng, radius_km, types):
    r_m = int(radius_km * 1000)
    blocks = []
    for t in types:
        for el in ("node", "way", "relation"):
            blocks.append(f'  {el}["amenity"="{t}"](around:{r_m},{lat},{lng});')
    body = "\n".join(blocks)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center tags;"


def fetch_schools(lat, lng, radius_km, types=("school",), retries=1):
    """Consulta o Overpass e retorna [(lat, lng, nome)] das escolas na área.

    Dedup por (type,id) do OSM e descarta pontos a < ~30 m de um já incluído (mesma
    escola aparecendo como node + way/relation).
    """
    import requests  # mesma dep usada em configs/boundary.py

    query = _build_query(lat, lng, radius_km, types)
    ua = {"User-Agent": "scraper99-crawler/1.0 (crawler de fila de escolas; OSM)"}
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, headers=ua, timeout=90)
            if r.status_code == 429:
                raise RuntimeError("429 (rate limit do Overpass)")
            r.raise_for_status()
            elements = r.json().get("elements", [])
            break
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"[schools] Overpass falhou ({e}); tentando de novo em 5s...")
                time.sleep(5)
            else:
                raise RuntimeError(f"Overpass falhou: {last_err}")

    pts = []
    seen_ids = set()
    for el in elements:
        oid = (el.get("type"), el.get("id"))
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        if el.get("type") == "node":
            la, lo = el.get("lat"), el.get("lon")
        else:  # way / relation -> usa o centro
            c = el.get("center") or {}
            la, lo = c.get("lat"), c.get("lon")
        if la is None or lo is None:
            continue
        la, lo = round(float(la), 6), round(float(lo), 6)
        name = (el.get("tags") or {}).get("name", "").strip() or "escola"
        name = name.replace("\n", " ").replace("\r", " ").strip()
        # descarta a mesma escola colada (< 30 m de uma já incluída)
        if any(_haversine_m((la, lo), (p[0], p[1])) < 30 for p in pts):
            continue
        pts.append((la, lo, name))
    return pts


def write_queue(points, out_path, append=False, meta=""):
    """Grava as escolas no arquivo de fila (lat,lng,nome). Default sobrescreve."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"# escolas OSM | {meta} | {len(points)} pontos\n"
    lines = [f"{la},{lo},{name}" for la, lo, name in points]
    body = header + "\n".join(lines) + ("\n" if lines else "")
    if append and out.exists():
        with out.open("a", encoding="utf-8") as fh:
            fh.write(body)
    else:
        out.write_text(body, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Coletor de escolas (OSM) -> fila do crawler 99")
    p.add_argument("--point", required=True, help='centro da área: "lat,lng"')
    p.add_argument("--radius", type=float, default=3.0, help="raio em km (default 3)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="arquivo de fila de saída")
    p.add_argument("--append", action="store_true", help="acrescenta em vez de sobrescrever")
    p.add_argument("--types", default="school",
                   help="amenities OSM separados por vírgula (default school)")
    a = p.parse_args()

    try:
        lat, lng = (float(x) for x in a.point.split(","))
    except Exception:
        print('--point inválido; use "lat,lng" (ex: "-16.6869,-49.2648")')
        sys.exit(2)
    types = tuple(t.strip() for t in a.types.split(",") if t.strip())

    print(f"[schools] buscando {types} num raio de {a.radius:g}km de {lat},{lng} (OSM/Overpass)...")
    pts = fetch_schools(lat, lng, a.radius, types)
    if not pts:
        print("[schools] 0 escolas encontradas — nada gravado. Tente um raio maior ou outro ponto.")
        sys.exit(1)

    meta = f"ponto={lat},{lng} raio={a.radius:g}km tipos={'/'.join(types)}"
    write_queue(pts, a.out, append=a.append, meta=meta)
    verbo = "acrescentadas a" if a.append else "gravadas em"
    print(f"[schools] {len(pts)} escola(s) {verbo} {a.out}")
    for la, lo, name in pts[:8]:
        print(f"    {la},{lo}  {name}")
    if len(pts) > 8:
        print(f"    ... (+{len(pts) - 8})")
    print(f"\nAgora rode:  python -m crawler.crawl_99 --queue {a.out} --delay 60 --resume")


if __name__ == "__main__":
    main()
