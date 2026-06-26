# Crawler 99 Food — automação por grade de localização

Camada de **automação** que roda o scraper em **vários endereços** automaticamente:
delimita uma área (cidade / bbox / bairro) → gera uma grade de pontos → em cada ponto
faz **mock GPS**, abre o app **dispensando os anúncios de abertura**, troca a entrega
para o ponto, e **chama o scraper** (`capture.ps1`) pra capturar o feed. Dedup global
por `shopId`, envio por ponto ao Tinybird.

> **Crawler ≠ Scraper.** O crawler (esta pasta) só orquestra a automação. A **captura**
> (heap-scan Frida + consolidação + Tinybird) é o `capture.ps1`/`hook_feed.js`/`consolidate.py`
> na raiz — reusados, não duplicados.

## Componentes

| Arquivo | Papel |
|---|---|
| `crawl_99.py` | orquestrador: área→grade→por ponto(mock→navega→captura)→dedup |
| `fakegps.py` | mock GPS: escreve o DataStore do XposedFakeLocation + Play (FAB) |
| `screen.py` | máquina de estados de tela: dispensa anúncios, detecta feed pronto, troca endereço |
| `configs/cities.py` | grade por cidade / bbox / bairro-OSM (`generate_*_grid`) |
| `configs/boundary.py` | polígono OSM (Nominatim) p/ filtrar a grade (`--boundary`/`--osm`) |
| `../capture.ps1` | **scraper**: captura pura de 1 ponto (heap-scan + consolidate + Tinybird) |
| `state/seen.json` | shopIds já vistos (dedup global, p/ `--resume`) |
| `NOTES.md` | diário do spike (mecanismo do mock, anti-tamper, coords das telas) |

## Pré-requisitos

1. **Scraper funcionando** (ver README da raiz): Frida **17.6.1** no PC e device, root, app 99 **logado**.
2. **Mock GPS = XposedFakeLocation >= v0.1.2** (a v0.0.x NÃO tem controle por broadcast).
   No app: **Settings → External Control → "Allow external broadcast control"** LIGADO;
   **Target Apps → marcar `99` (com.taxis99)** e ligar **"Enable system-level hooks"**
   (cobre Google Play Services/fused — o 99 usa fused location). Reabrir o 99 uma vez.
   Verifique com `python crawler/fakegps.py --check` (deve dar `True`).
   O crawler seta a localização via broadcast (`fakegps.set_location`) — sem tocar na UI.
3. Python: `pip install pillow` (telas WebView por screenshot). Opcional p/ `--boundary`/`--osm`:
   `pip install requests shapely`.

## Uso

```powershell
python -m crawler.crawl_99 --list-cities

# testar o pipeline SEM mock (1 ponto, na localização atual do device):
python -m crawler.crawl_99 --here --dry-run --cycles 2 --swipes 4

# crawl real de uma cidade (precisa do mock OK):
python -m crawler.crawl_99 --city rio-de-janeiro --step 3 --max-points 10

# bairro via polígono OSM:
python -m crawler.crawl_99 --osm "Tijuca, Rio de Janeiro, BR" --step 1.5 --resume

# bounding box custom:
python -m crawler.crawl_99 --bbox=-22.94,-22.91,-43.26,-43.21 --step 1.5
```

| Flag | Default | O que faz |
|---|---|---|
| `--city` / `--bbox` / `--osm` / `--here` | — | como delimitar a área |
| `--step` | padrão da cidade / 3km | espaçamento da grade (km) |
| `--boundary` | off | filtra a grade pelo polígono OSM do município |
| `--max-points` | 0 (todos) | limita nº de pontos |
| `--resume` | off | retoma o dedup (`state/seen.json`) |
| `--here` | off | 1 ponto na localização atual, **sem mock** (teste de pipeline) |
| `--cycles` / `--swipes` | 8 / 6 | profundidade do scroll+heap-scan por ponto |
| `--dry-run` | off | não envia ao Tinybird (gera preview) |

## Fluxo por ponto (mock ativo)

```
fakegps.activate(lat,lng)            # força-parada do FakeLocation, escreve coord, abre, Play (FAB)
  └ screen.wait_ready()              # force-stop+relaunch 99, dispensa anúncios, detecta feed
     └ screen.select_current_location()  # endereço → "usar minha localização" → confirma pin
        └ capture.ps1 -Lat -Lng      # heap-scan + consolidate + tinybird (POI real do AddressStorage)
           └ dedup por shopId        # state/seen.json
```

## Status (2026-06-24)

- ✅ `fakegps`, `configs`, `capture.ps1`, `screen.py` (launch+dispensa anúncios+feed pronto), `crawl_99` — **validados**.
- ✅ Pipeline e2e provado em `--here --dry-run` (40 lojas, dedup, preview).
- ⏳ **Pendente**: o mock injetar no `com.taxis99` (escopo LSPosed: 99 + Google Play Services).
  Sem isso o `select_current_location` resolve a localização real. Ver `NOTES.md`.
