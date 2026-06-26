"""
cities.py — geração da grade de coordenadas que o crawler 99 vai percorrer.

Adaptado do crawler de iFood do usuário (Documents/ifood-intercept/configs/cities.py).
Três formas de delimitar a área:
  - cidade pré-definida  -> generate_city_grid('rio-de-janeiro')
  - bounding box custom  -> generate_bbox_grid(lat_min, lat_max, lon_min, lon_max, step_km)
  - bairro/área via OSM   -> generate_osm_grid('Tijuca, Rio de Janeiro, BR', step_km)
                            (usa configs/boundary.py p/ pegar o polígono e filtrar a grade)

Espaçamento (step_km) ~ raio de entrega (2-4 km) p/ não deixar buraco entre pontos.
"""

import math

LAT_KM = 111.32  # 1° de latitude ≈ 111.32 km

CITIES: dict[str, dict] = {
    "rio-de-janeiro": {
        "name": "Rio de Janeiro - RJ",
        "lat_min": -23.082, "lat_max": -22.746,
        "lon_min": -43.795, "lon_max": -43.101,
        "step_km": 4.0,
        "osm_query": "Rio de Janeiro, RJ, Brazil",
    },
    "sao-paulo": {
        "name": "São Paulo - SP",
        "lat_min": -24.008, "lat_max": -23.357,
        "lon_min": -46.826, "lon_max": -46.365,
        "step_km": 5.0,
        "osm_query": "São Paulo, SP, Brazil",
    },
    "porto-alegre": {
        "name": "Porto Alegre - RS",
        "lat_min": -30.252, "lat_max": -29.935,
        "lon_min": -51.290, "lon_max": -51.054,
        "step_km": 4.0,
        "osm_query": "Porto Alegre, RS, Brazil",
    },
    "curitiba": {
        "name": "Curitiba - PR",
        "lat_min": -25.650, "lat_max": -25.332,
        "lon_min": -49.385, "lon_max": -49.192,
        "step_km": 4.0,
        "osm_query": "Curitiba, PR, Brazil",
    },
    "sao-jose-dos-pinhais": {
        "name": "São José dos Pinhais - PR",
        "lat_min": -25.620, "lat_max": -25.480,
        "lon_min": -49.260, "lon_max": -49.120,
        "step_km": 3.0,
        "osm_query": "São José dos Pinhais, PR, Brazil",
    },
    "goiania": {
        "name": "Goiânia - GO",
        "lat_min": -16.768, "lat_max": -16.598,
        "lon_min": -49.352, "lon_max": -49.176,
        "step_km": 4.0,
        "osm_query": "Goiânia, GO, Brazil",
    },
}


def _rect_grid(lat_min, lat_max, lon_min, lon_max, step_km):
    """Grade retangular cobrindo o bbox. Retorna [(lat, lon)] com 6 casas."""
    lat_step = step_km / LAT_KM
    mid_lat = (lat_min + lat_max) / 2
    lon_step = step_km / (LAT_KM * math.cos(math.radians(mid_lat)))
    points = []
    lat = lat_max
    while lat >= lat_min:
        lon = lon_min
        while lon <= lon_max:
            points.append((round(lat, 6), round(lon, 6)))
            lon += lon_step
        lat -= lat_step
    return points


def _apply_boundary(points, osm_query, city_key):
    """Filtra pontos fora do polígono real (OSM). Requer shapely/requests."""
    from .boundary import fetch_city_boundary
    from shapely.geometry import Point
    poly = fetch_city_boundary(city_key, osm_query)
    before = len(points)
    pts = [p for p in points if Point(p[1], p[0]).within(poly)]
    print(f"[boundary] {before} -> {len(pts)} pontos ({before - len(pts)} fora do polígono)")
    return pts


def generate_city_grid(city_key, step_km=None, use_boundary=False):
    if city_key not in CITIES:
        raise ValueError(f"Cidade '{city_key}' não encontrada. Opções: {', '.join(CITIES)}")
    cfg = CITIES[city_key]
    step = step_km if step_km is not None else cfg["step_km"]
    pts = _rect_grid(cfg["lat_min"], cfg["lat_max"], cfg["lon_min"], cfg["lon_max"], step)
    if use_boundary:
        pts = _apply_boundary(pts, cfg["osm_query"], city_key)
    return pts


def generate_bbox_grid(lat_min, lat_max, lon_min, lon_max, step_km=3.0):
    """Área custom por bounding box (sem boundary OSM)."""
    return _rect_grid(lat_min, lat_max, lon_min, lon_max, step_km)


def generate_osm_grid(osm_query, step_km=3.0, cache_key=None):
    """Bairro/área via OSM: pega o polígono, gera bbox dele e filtra pelo polígono."""
    from .boundary import fetch_city_boundary
    from shapely.geometry import Point
    key = cache_key or osm_query.lower().replace(",", "").replace(" ", "-")[:40]
    poly = fetch_city_boundary(key, osm_query)
    minx, miny, maxx, maxy = poly.bounds  # (lon_min, lat_min, lon_max, lat_max)
    pts = _rect_grid(miny, maxy, minx, maxx, step_km)
    before = len(pts)
    pts = [p for p in pts if Point(p[1], p[0]).within(poly)]
    print(f"[osm] '{osm_query}': {before} -> {len(pts)} pontos dentro do polígono")
    return pts


if __name__ == "__main__":
    print(f"{'Chave':<24}{'Cidade':<28}{'Step':<7}{'Pontos'}")
    print("-" * 70)
    for k, c in CITIES.items():
        print(f"{k:<24}{c['name']:<28}{c['step_km']:<7.1f}{len(generate_city_grid(k))}")
