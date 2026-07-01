"""
queue.py — fila explícita de endereços (coordenadas) para o crawler 99.

Fonte de pontos ALTERNATIVA ao sistema de cidades (configs/cities.py): em vez de gerar
uma grade retangular sobre uma área, o usuário lista as coordenadas que quer bater num
arquivo .txt e o crawler percorre uma a uma (mock -> scroll/captura -> próxima).

Formato do .txt (uma coordenada por linha):
    lat,lng[,rótulo]
  - linhas vazias e as que começam com '#' são ignoradas;
  - o 3º campo (rótulo) é opcional e serve só p/ identificar o ponto nos logs.
Ex.:
    # fila Goiânia
    -16.6869,-49.2648,Centro
    -16.7050,-49.2700,Setor Bueno
    -16.6750,-49.2550

Progresso (resume): as coords já concluídas são gravadas em
  crawler/state/<nome-da-fila>.done  ("lat,lng" por linha), p/ pular ao re-rodar.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"


def _key(lat, lng):
    """Chave canônica de uma coordenada (6 casas), usada no resume."""
    return f"{round(float(lat), 6)},{round(float(lng), 6)}"


def load_queue(path):
    """Lê o .txt e devolve [(lat, lng, label)] (label = '' quando ausente).

    Linhas vazias / comentário ('#') são ignoradas; linhas malformadas ou com coords
    fora de faixa geram aviso e são puladas.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"arquivo de fila não encontrado: {p}")
    pts = []
    for n, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) < 2:
            print(f"[queue] linha {n} ignorada (faltam coords): {raw!r}")
            continue
        try:
            lat, lng = float(parts[0]), float(parts[1])
        except ValueError:
            print(f"[queue] linha {n} ignorada (coords inválidas): {raw!r}")
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            print(f"[queue] linha {n} ignorada (fora de faixa): {raw!r}")
            continue
        label = ",".join(parts[2:]).strip() if len(parts) > 2 else ""
        pts.append((round(lat, 6), round(lng, 6), label))
    return pts


def progress_path(queue_path):
    """Arquivo de progresso isolado por fila: crawler/state/<nome-da-fila>.done."""
    return STATE / (Path(queue_path).name + ".done")


def load_done(queue_path):
    """Set de chaves 'lat,lng' já concluídas em execuções anteriores desta fila."""
    f = progress_path(queue_path)
    if not f.exists():
        return set()
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()}


def mark_done(queue_path, lat, lng):
    """Anexa a coordenada concluída ao arquivo de progresso desta fila."""
    STATE.mkdir(exist_ok=True)
    with progress_path(queue_path).open("a", encoding="utf-8") as fh:
        fh.write(_key(lat, lng) + "\n")
