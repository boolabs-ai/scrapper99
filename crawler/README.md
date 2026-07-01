# Crawler 99 Food — automação por grade de localização

Camada de **automação** que roda o scraper em **vários endereços** automaticamente.
Duas formas de definir os pontos:
- **Área** (cidade / bbox / bairro) → gera uma **grade** de pontos; ou
- **Fila** (`--queue arquivo.txt`) → você lista as coordenadas que quer bater, uma por linha.

Em cada ponto faz **mock GPS**, abre o app **dispensando os anúncios de abertura**, troca a
entrega para o ponto, e **chama o scraper** (`capture.ps1`) pra capturar o feed. Dedup global
por `shopId`, envio por ponto ao Tinybird.

> **Crawler ≠ Scraper.** O crawler (esta pasta) só orquestra a automação. A **captura**
> (heap-scan Frida + consolidação + Tinybird) é o `capture.ps1`/`hook_feed.js`/`consolidate.py`
> na raiz — reusados, não duplicados.

## Componentes

| Arquivo | Papel |
|---|---|
| `crawl_99.py` | orquestrador: área/fila→por ponto(mock→navega→captura)→dedup; menu interativo |
| `fakegps.py` | mock GPS via broadcast do XposedFakeLocation (`set_location`) |
| `screen.py` | máquina de estados de tela: dispensa anúncios, detecta feed pronto, troca endereço |
| `fila.py` | **fila de endereços**: lê o txt (`lat,lng[,rótulo]`) + progresso p/ resume |
| `queue.example.txt` | modelo de fila (copie p/ `queue.txt`) |
| `schools.py` | coletor de **escolas** (OSM/Overpass) numa área → gera o `queue.txt` |
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
# INTERATIVO: sem flags, abre o menu de modo (fila/cidade/bbox/bairro) e pergunta os parâmetros
python -m crawler.crawl_99

python -m crawler.crawl_99 --list-cities

# FILA de endereços (txt): bate cada coord, 60s entre pontos, retomando de onde parou
python -m crawler.crawl_99 --queue crawler/queue.txt --delay 60 --resume

# testar o pipeline SEM mock (1 ponto, na localização atual do device):
python -m crawler.crawl_99 --here --dry-run --cycles 2 --swipes 4

# crawl real de uma cidade (precisa do mock OK):
python -m crawler.crawl_99 --city goiania --step 4 --max-points 10 --delay 60

# bairro via polígono OSM:
python -m crawler.crawl_99 --osm "Setor Bueno, Goiânia, BR" --step 1.5 --resume
```

> Passar **qualquer** flag de modo (`--queue/--city/--bbox/--osm/--here/--list-cities`) pula o
> menu interativo — bom para rodar agendado/automatizado.

### Fila de endereços (`--queue`)

Arquivo `.txt`, **uma coordenada por linha**: `lat,lng[,rótulo]`. Linhas vazias e começadas
com `#` são ignoradas; o rótulo (3º campo) é opcional e só aparece nos logs. Modelo em
[`queue.example.txt`](queue.example.txt):

```
# fila Goiânia
-16.6869,-49.2648,Centro
-16.7050,-49.2700,Setor Bueno
-16.6750,-49.2550
```

Com `--resume`, as coords concluídas são gravadas em `state/<nome-da-fila>.done` e puladas no
próximo run (essencial quando o **rate limit do 99** força parar no meio).

#### Gerar a fila a partir de escolas (OSM)

`schools.py` monta a fila com as **escolas de uma área** (OpenStreetMap/Overpass, `amenity=school`),
dado um **ponto + raio**:

```powershell
# 1) escolas num raio de 3km do ponto -> crawler/queue.txt
python -m crawler.schools --point "-16.6869,-49.2648" --radius 3

# variações: outro arquivo, acrescentar, ampliar tipos
python -m crawler.schools --point "-16.69,-49.26" --radius 5 --out crawler/queue.txt --append
python -m crawler.schools --point "-16.69,-49.26" --types school,college,kindergarten

# 2) bater cada escola com o crawler on-device (passo separado)
python -m crawler.crawl_99 --queue crawler/queue.txt --delay 60 --resume
```

| Flag | Default | O que faz |
|---|---|---|
| `--point "lat,lng"` | — (obrig.) | centro da área |
| `--radius <km>` | 3 | raio de busca das escolas |
| `--out <arquivo>` | `crawler/queue.txt` | fila de saída |
| `--append` | off | acrescenta em vez de sobrescrever |
| `--types <csv>` | `school` | amenities OSM (ex: `school,college,kindergarten`) |

Self-contained: usa só o OSM (não precisa do 99/proxy). Os nomes das escolas viram o rótulo de
cada ponto da fila. > **De onde veio:** o `signer4` (serviço dos superiores) sonda o feed do 99
sobre uma lista de escolas em GeoJSON cuja origem é o OSM — aqui replicamos só a coleta das
escolas (via Overpass) e alimentamos o nosso crawler on-device.

| Flag | Default | O que faz |
|---|---|---|
| `--queue <arquivo>` | — | fila de coords por txt (`lat,lng[,rótulo]`) |
| `--city` / `--bbox` / `--osm` / `--here` | — | como delimitar a área (alternativa à fila) |
| `--step` | padrão da cidade / 3km | espaçamento da grade (km) |
| `--boundary` | off | filtra a grade pelo polígono OSM do município |
| `--max-points` | 0 (todos) | limita nº de pontos |
| `--resume` | off | retoma dedup (`state/seen.json`) e a fila (`state/<fila>.done`) |
| `--delay <s>` | 0 | pausa entre pontos (anti rate-limit do 99) |
| `--here` | off | 1 ponto na localização atual, **sem mock** (teste de pipeline) |
| `--cycles` / `--swipes` | 12 / 6 | profundidade do scroll+heap-scan por ponto (scroll forte) |
| `--dry-run` | off | não envia ao Tinybird (gera preview) |

## Fluxo por ponto (mock ativo)

```
fakegps.activate(lat,lng)            # broadcast SET_LOCATION p/ o XposedFakeLocation
  └ screen.wait_ready()              # force-stop+relaunch 99, vai p/ aba Food, dispensa anúncios
                                     #   (mock + force-stop já fazem o feed seguir a localização)
     └ capture.ps1 -Lat -Lng        # scroll + heap-scan + consolidate + tinybird (POI do AddressStorage)
        └ dedup por shopId          # state/seen.json (+ state/<fila>.done p/ --resume)
```

> O `screen.select_current_location()` (trocar/salvar endereço via "usar minha localização")
> existe mas NÃO é usado no fluxo — o mock + force-stop bastam. Só seria necessário se o
> endereço de entrega não estivesse em modo "usar minha localização".

## Status (2026-06-29)

- ✅ **Mock GPS validado e2e** (Rio→Goiânia): XposedFakeLocation via LSPosed cobrindo o fused
  provider do GMS. **Requer o `meta-overlayfs` (metamodule)** p/ os módulos montarem no
  SukiSU/ReSukiSU — sem ele o LSPosed não carrega o XFL e o 99 lê o GPS real. Ver `NOTES.md`.
- ✅ Crawler e2e: 1 ponto em Goiânia → 30 lojas, dedup, envio ao Tinybird (202 OK).
- ✅ **Fila de endereços** (`--queue`) + **menu interativo** + `--delay`/resume da fila.
- ⏳ Grade/fila multi-ponto com envio real: usar `--delay` (≥60s) por causa do **rate limit do 99**.
