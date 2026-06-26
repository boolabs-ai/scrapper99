"""
crawl_99.py — orquestrador do crawler 99 Food (camada de AUTOMAÇÃO).

Delimita uma área (cidade / bbox / bairro-OSM) -> gera grade de pontos -> por ponto:
  1. mock GPS no ponto         (crawler/fakegps.activate)
  2. abre o 99 e deixa o feed pronto, dispensando anúncios   (crawler/screen.wait_ready)
  3. troca a entrega p/ "usar minha localização" (= o ponto mockado) (screen.select_current_location)
  4. CAPTURA o feed do ponto   (capture.ps1 — lado scraper; heap-scan + Tinybird)
  5. dedup global por shopId   (crawler/state/seen.json, p/ --resume)

Mantém crawler (automação) separado do scraper (captura): aqui só orquestra e CHAMA o capture.ps1.

PRÉ-REQUISITO p/ o mock: no LSPosed, o XposedFakeLocation precisa ter no ESCOPO
  com.taxis99 + Google Play Services (com.google.android.gms) + System Framework.

Uso:
  python -m crawler.crawl_99 --list-cities
  python -m crawler.crawl_99 --here                 # 1 ponto na localização ATUAL (testa pipeline s/ mock)
  python -m crawler.crawl_99 --city rio-de-janeiro --step 3 --max-points 5
  python -m crawler.crawl_99 --osm "Tijuca, Rio de Janeiro, BR" --step 1.5 --resume
  python -m crawler.crawl_99 --bbox=-22.94,-22.91,-43.26,-43.21 --step 1.5 --dry-run
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import fakegps, screen
from .configs import cities

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATE = HERE / "state"
SEEN_FILE = STATE / "seen.json"
CAPTURE_PS1 = ROOT / "capture.ps1"


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    STATE.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def shop_ids_from_output():
    """shopIds do restaurantes.json gerado pelo último capture."""
    f = ROOT / "restaurantes.json"
    if not f.exists():
        return set()
    try:
        return {str(s.get("shopId")) for s in json.loads(f.read_text(encoding="utf-8")) if s.get("shopId")}
    except Exception:
        return set()


def run_capture(lat, lng, cycles, swipes, device, dry_run):
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CAPTURE_PS1),
            "-Lat", str(lat), "-Lng", str(lng), "-Cycles", str(cycles),
            "-SwipesPerCycle", str(swipes), "-DeviceId", device]
    if dry_run:
        args.append("-DryRun")
    return subprocess.run(args).returncode


def build_grid(a):
    if a.list_cities:
        for k, c in cities.CITIES.items():
            print(f"  {k:<24} {c['name']:<26} step {c['step_km']}km  ~{len(cities.generate_city_grid(k))} pts")
        sys.exit(0)
    if a.here:
        return [None]  # ponto único = localização atual (sem mock)
    if a.bbox:
        lo = [float(x) for x in a.bbox.split(",")]
        return cities.generate_bbox_grid(lo[0], lo[1], lo[2], lo[3], a.step or 3.0)
    if a.osm:
        return cities.generate_osm_grid(a.osm, a.step or 3.0)
    if a.city:
        return cities.generate_city_grid(a.city, a.step, use_boundary=a.boundary)
    print("informe --city / --bbox / --osm / --here (ou --list-cities)")
    sys.exit(2)


def main():
    p = argparse.ArgumentParser(description="Crawler 99 Food por grade de localização")
    p.add_argument("--city")
    p.add_argument("--bbox", help="lat_min,lat_max,lon_min,lon_max")
    p.add_argument("--osm", help='ex: "Tijuca, Rio de Janeiro, BR"')
    p.add_argument("--step", type=float, help="espaçamento da grade em km")
    p.add_argument("--boundary", action="store_true", help="filtra grade pelo polígono OSM da cidade")
    p.add_argument("--max-points", type=int, default=0)
    p.add_argument("--resume", action="store_true", help="retoma dedup de execução anterior")
    p.add_argument("--here", action="store_true", help="1 ponto na localização ATUAL (sem mock)")
    p.add_argument("--cycles", type=int, default=8)
    p.add_argument("--swipes", type=int, default=6)
    p.add_argument("--device", default="99_food_app")
    p.add_argument("--dry-run", action="store_true", help="não envia ao Tinybird (preview)")
    p.add_argument("--list-cities", action="store_true")
    a = p.parse_args()

    grid = build_grid(a)
    if a.max_points and not a.here:
        grid = grid[:a.max_points]
    seen = load_seen() if a.resume else set()
    print(f"[crawl] {len(grid)} ponto(s); dedup inicial: {len(seen)} shopIds"
          + (" | MODO --here (sem mock)" if a.here else ""))

    for i, pt in enumerate(grid, 1):
        label = "ATUAL" if pt is None else f"{pt[0]},{pt[1]}"
        print(f"\n=== ponto {i}/{len(grid)}  ({label}) ===")
        try:
            if pt is not None:
                print("[crawl] mock GPS ->", label)
                fakegps.activate(pt[0], pt[1])

            if not screen.wait_ready(timeout=90):
                print("[crawl] feed não ficou pronto; pulando ponto.")
                continue

            if pt is not None:
                print("[crawl] selecionando 'usar minha localização'...")
                screen.select_current_location()
                if not screen.wait_ready(timeout=60, relaunch=False):
                    print("[crawl] feed não recarregou após trocar endereço; pulando.")
                    continue

            # coords p/ rotular a captura: o ponto (ou as do device no --here)
            lat = pt[0] if pt is not None else 0
            lng = pt[1] if pt is not None else 0
            rc = run_capture(lat, lng, a.cycles, a.swipes, a.device, a.dry_run)
            print(f"[crawl] capture exit={rc}  endereço={screen.address_text()!r}")

            ids = shop_ids_from_output()
            new = ids - seen
            seen |= ids
            save_seen(seen)
            print(f"[crawl] ponto trouxe {len(ids)} lojas, {len(new)} novas | total único: {len(seen)}")
        except KeyboardInterrupt:
            print("\n[crawl] interrompido pelo usuário."); break
        except Exception as e:
            print(f"[crawl] erro no ponto {label}: {e}")

    if not a.here:
        fakegps.stop()
    print(f"\n[crawl] FIM. shopIds únicos acumulados: {len(seen)}  (state/seen.json)")


if __name__ == "__main__":
    main()
