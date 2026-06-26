"""
boundary.py — polígono municipal/bairro via Nominatim (OSM), com cache local.

Adaptado de Documents/ifood-intercept/configs/boundary.py.
Cache em crawler/configs/cache/{key}.geojson (evita re-fetch).

Requer: requests, shapely  (pip install requests shapely)
Opcional: só é usado quando o crawler roda com --boundary ou --osm.
"""

import json
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

CACHE_DIR = Path(__file__).parent / "cache"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "scraper99-crawler/1.0"}


def fetch_city_boundary(cache_key: str, osm_query: str) -> BaseGeometry:
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.geojson"
    if cache_file.exists():
        return shape(json.loads(cache_file.read_text(encoding="utf-8")))

    print(f'[boundary] buscando polígono OSM: "{osm_query}"...')
    resp = requests.get(NOMINATIM_URL, params={
        "q": osm_query, "format": "geojson",
        "polygon_geojson": "1", "limit": "1",
    }, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    feats = resp.json().get("features", [])
    if not feats:
        raise ValueError(f"Nominatim não achou '{osm_query}'")
    geom = feats[0]["geometry"]
    if geom["type"] not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"OSM retornou '{geom['type']}' (não polígono) p/ '{osm_query}'")
    cache_file.write_text(json.dumps(geom, ensure_ascii=False), encoding="utf-8")
    print(f"[boundary] cache salvo: {cache_file.name}")
    return shape(geom)
