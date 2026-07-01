"""
crawl_99.py — orquestrador do crawler 99 Food (camada de AUTOMAÇÃO).

Define os pontos por FILA (--queue arquivo.txt) ou por ÁREA (cidade / bbox / bairro-OSM
-> grade). Por ponto:
  1. mock GPS no ponto         (crawler/fakegps.activate)
  2. force-stop + reabre o 99 e deixa o feed pronto na aba Food, dispensando anúncios
     (crawler/screen.wait_ready) — o mock + force-stop já fazem o feed seguir a localização
  3. CAPTURA o feed do ponto   (capture.ps1 — lado scraper; heap-scan + Tinybird)
  4. dedup global por shopId   (crawler/state/seen.json) + progresso da fila (--resume)

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

from . import fakegps, screen, fila
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
    if a.queue:
        return fila.load_queue(a.queue)
    if a.bbox:
        lo = [float(x) for x in a.bbox.split(",")]
        return cities.generate_bbox_grid(lo[0], lo[1], lo[2], lo[3], a.step or 3.0)
    if a.osm:
        return cities.generate_osm_grid(a.osm, a.step or 3.0)
    if a.city:
        return cities.generate_city_grid(a.city, a.step, use_boundary=a.boundary)
    print("informe --queue / --city / --bbox / --osm / --here (ou --list-cities)")
    sys.exit(2)


def _ask(prompt, default=""):
    """input() com valor default mostrado entre [] (Enter aceita o default)."""
    sufx = f" [{default}]" if default != "" else ""
    try:
        v = input(f"{prompt}{sufx}: ").strip()
    except EOFError:
        v = ""
    return v or default


def interactive_setup(a):
    """Menu de seleção de modo quando nenhum modo foi passado por flag (e há TTY).

    Preenche o namespace `a` conforme a escolha. Se já veio modo por flag, não faz nada
    (CLI/automação intactos).
    """
    if a.queue or a.city or a.bbox or a.osm or a.here or a.list_cities:
        return
    if not sys.stdin.isatty():
        return  # sem terminal interativo: deixa o build_grid reclamar e sair

    print("\nEscolha o modo:")
    print("  1) Fila de endereços (arquivo txt)")
    print("  2) Cidade pré-definida")
    print("  3) Bounding box")
    print("  4) Bairro/área (OSM)")
    modo = _ask(">", "1")

    if modo == "1":
        a.queue = _ask("Arquivo da fila", str(HERE / "queue.txt"))
    elif modo == "2":
        keys = list(cities.CITIES)
        for i, k in enumerate(keys, 1):
            print(f"  {i}) {k}  ({cities.CITIES[k]['name']})")
        sel = _ask("Cidade (número ou chave)", "1")
        a.city = keys[int(sel) - 1] if sel.isdigit() and 1 <= int(sel) <= len(keys) else sel
        step = _ask("Step km (Enter = padrão da cidade)", "")
        a.step = float(step) if step else None
    elif modo == "3":
        a.bbox = _ask("bbox lat_min,lat_max,lon_min,lon_max", "")
        a.step = float(_ask("Step km", "3"))
    elif modo == "4":
        a.osm = _ask('Bairro/área OSM (ex: "Setor Bueno, Goiânia, BR")', "")
        a.step = float(_ask("Step km", "3"))
        a.boundary = True
    else:
        print("modo inválido."); sys.exit(2)

    # comuns a todos os modos
    a.delay = float(_ask("Delay entre pontos (s)", "60"))
    a.resume = _ask("Retomar de onde parou? (S/n)", "S").lower().startswith("s")
    a.dry_run = _ask("Dry-run (não envia ao Tinybird)? (s/N)", "N").lower().startswith("s")
    a.max_points = int(_ask("Máx. de pontos (0 = todos)", "0"))


def main():
    p = argparse.ArgumentParser(description="Crawler 99 Food por grade de localização")
    p.add_argument("--queue", help="arquivo txt com a fila de coords (lat,lng[,rótulo] por linha)")
    p.add_argument("--city")
    p.add_argument("--bbox", help="lat_min,lat_max,lon_min,lon_max")
    p.add_argument("--osm", help='ex: "Tijuca, Rio de Janeiro, BR"')
    p.add_argument("--step", type=float, help="espaçamento da grade em km")
    p.add_argument("--boundary", action="store_true", help="filtra grade pelo polígono OSM da cidade")
    p.add_argument("--max-points", type=int, default=0)
    p.add_argument("--resume", action="store_true", help="retoma dedup/fila de execução anterior")
    p.add_argument("--here", action="store_true", help="1 ponto na localização ATUAL (sem mock)")
    p.add_argument("--cycles", type=int, default=12)
    p.add_argument("--swipes", type=int, default=6)
    p.add_argument("--delay", type=float, default=0.0, help="pausa em segundos entre pontos (anti rate-limit)")
    p.add_argument("--device", default="99_food_app")
    p.add_argument("--dry-run", action="store_true", help="não envia ao Tinybird (preview)")
    p.add_argument("--list-cities", action="store_true")
    a = p.parse_args()

    interactive_setup(a)  # menu de modo se nenhum foi passado por flag (e há TTY)

    grid = build_grid(a)
    if a.queue and a.resume:
        done = fila.load_done(a.queue)
        before = len(grid)
        grid = [pt for pt in grid if fila._key(pt[0], pt[1]) not in done]
        if before != len(grid):
            print(f"[crawl] resume: {before - len(grid)} coord(s) já batidas puladas")
    if a.max_points and not a.here:
        grid = grid[:a.max_points]
    seen = load_seen() if a.resume else set()
    print(f"[crawl] {len(grid)} ponto(s); dedup inicial: {len(seen)} shopIds"
          + (" | MODO --here (sem mock)" if a.here else "")
          + (f" | delay {a.delay:g}s" if a.delay else ""))

    for i, pt in enumerate(grid, 1):
        if pt is None:
            label = "ATUAL"
        else:
            label = pt[2] if len(pt) > 2 and pt[2] else f"{pt[0]},{pt[1]}"
        print(f"\n=== ponto {i}/{len(grid)}  ({label}) ===")
        try:
            if pt is not None:
                print("[crawl] mock GPS ->", label)
                fakegps.activate(pt[0], pt[1])

            if not screen.wait_ready(timeout=150):
                print("[crawl] feed não ficou pronto; pulando ponto.")
                continue

            # o mock GPS + force-stop já fazem o feed seguir a localização (app em modo
            # "usar minha localização"); não re-seleciona/salva endereço por ponto.

            # coords p/ rotular a captura: o ponto (ou as do device no --here)
            lat = pt[0] if pt is not None else 0
            lng = pt[1] if pt is not None else 0
            rc = run_capture(lat, lng, a.cycles, a.swipes, a.device, a.dry_run)
            print(f"[crawl] capture exit={rc}  endereço={screen.address_text()!r}")

            ids = shop_ids_from_output()
            new = ids - seen
            seen |= ids
            save_seen(seen)
            if a.queue and pt is not None:
                fila.mark_done(a.queue, lat, lng)
            print(f"[crawl] ponto trouxe {len(ids)} lojas, {len(new)} novas | total único: {len(seen)}")
        except KeyboardInterrupt:
            print("\n[crawl] interrompido pelo usuário."); break
        except Exception as e:
            print(f"[crawl] erro no ponto {label}: {e}")

        if a.delay and i < len(grid):
            print(f"[crawl] aguardando {a.delay:g}s antes do próximo ponto...")
            time.sleep(a.delay)

    if not a.here:
        fakegps.stop()
    print(f"\n[crawl] FIM. shopIds únicos acumulados: {len(seen)}  (state/seen.json)")


if __name__ == "__main__":
    main()
