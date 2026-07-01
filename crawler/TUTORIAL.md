# Tutorial — Crawler 99 Food (passo a passo)

Guia prático de como o crawler funciona e como usá-lo, nos dois modos:
**Fila de endereços** (lista de coordenadas / escolas) e **Lista de cidades** (grade de área).

---

## 1. O que o crawler faz (visão geral)

O crawler é a camada de **automação** em cima do scraper (captura). Ele percorre vários
pontos geográficos automaticamente e, em **cada ponto**:

1. **Mock GPS** — coloca o celular naquela coordenada (módulo XposedFakeLocation, via broadcast).
2. **Force-stop + reabre o 99** — pra ele pegar a nova localização (o mock + force-stop já
   fazem o feed seguir a coordenada).
3. **Vai pra aba "Food"** — o 99 abre na aba Corrida; o crawler troca pra Food sozinho.
4. **Dispensa os anúncios** de abertura e espera o feed carregar.
5. **Rola o feed** (scroll forte) e **captura** (heap-scan com Frida) → consolida → **envia ao Tinybird**.
6. **Dedup global** por `shopId` e **marca o progresso** (pra poder retomar).
7. **Espera o `--delay`** e vai pro próximo ponto.

> Se um toque acidental abrir um restaurante durante o scroll, o crawler detecta e volta
> pro feed sozinho (`Ensure-Feed` no `capture.ps1`).

> **Crawler ≠ Scraper.** O crawler só orquestra; a captura é o `capture.ps1` (heap-scan +
> consolidate + Tinybird). Eles são separados de propósito.

---

## 2. Pré-requisitos (fazer uma vez)

**Celular (rooteado):**
- Conectado via USB e autorizado (`adb devices` mostra o aparelho).
- App **99 instalado e LOGADO** (sessão ativa — se deslogar, o feed não carrega).
- **Stack de mock GPS funcionando** (ver memória `mock-gps-stack-funcional`):
  - **XposedFakeLocation** ativo no LSPosed, com escopo em **`com.taxis99` + Google Play Services**;
  - Settings do XFL → **"Allow external broadcast control"** LIGADO;
  - **`meta-overlayfs` (metamodule) instalado** no ReSukiSU/SukiSU — sem ele os módulos não
    montam e o mock não chega ao 99.

**PC (Windows):**
- **Frida 17.6.1** configurado (mesmo do scraper — ver README da raiz).
- Python com: `pip install pillow requests` (e `shapely` se for usar `--osm`/`--boundary`).

**Conferir rápido se o mock está OK:**
```powershell
python crawler/fakegps.py --check       # deve dar "ControlReceiver presente: True"
```

---

## 3. MODO FILA — bater uma lista de coordenadas (ex: escolas)

Use quando você tem **pontos específicos** pra bater (escolas, endereços, POIs).

### Passo 1 — Montar a fila

**Opção A — escolas de uma área (OpenStreetMap):**
```powershell
python -m crawler.schools --point "-22.9249,-43.2326" --radius 3
```
- `--point "lat,lng"` = centro da área · `--radius` = raio em km.
- Busca todas as escolas (`amenity=school`) no raio e grava em `crawler/queue.txt`
  (formato `lat,lng,nome`), com o nome da escola como rótulo.
- Outras opções: `--out outro.txt`, `--append` (acrescenta), `--types school,college,kindergarten`.

**Opção B — escrever a fila à mão:**
Crie/edite `crawler/queue.txt` — uma coordenada por linha:
```
# comentários começam com #
-22.9249,-43.2326,Praça Saens Peña
-22.9211,-43.2376,Instituto Tear
-22.9170,-43.2442
```
O 3º campo (rótulo) é opcional. (Veja o modelo em `crawler/queue.example.txt`.)

### Passo 2 — Rodar a fila

**Teste primeiro com 1 ponto, sem enviar (dry-run):**
```powershell
python -m crawler.crawl_99 --queue crawler/queue.txt --max-points 1 --dry-run
```

**Rodar de verdade (envio ao Tinybird):**
```powershell
python -m crawler.crawl_99 --queue crawler/queue.txt --delay 90 --resume
```
- `--delay 90` = espera 90s entre escolas (**evita o rate limit do 99** — importante!).
- `--resume` = retoma de onde parou (pula as escolas já batidas).
- `--max-points 5` = limita a 5 pontos (opcional, bom pra testar aos poucos).

---

## 4. MODO CIDADE — cobrir uma área inteira (grade)

Use quando quer varrer **uma cidade/bairro inteiro** com uma grade de pontos.

### Passo 1 — Ver as cidades disponíveis
```powershell
python -m crawler.crawl_99 --list-cities
```
(rio-de-janeiro, sao-paulo, porto-alegre, curitiba, sao-jose-dos-pinhais, goiania)

### Passo 2 — Rodar
**Cidade pré-definida:**
```powershell
python -m crawler.crawl_99 --city goiania --step 4 --delay 90 --resume
```
- `--step 4` = espaçamento da grade em km (menor = mais pontos, mais cobertura).

**Bairro/área por nome (polígono do OpenStreetMap):**
```powershell
python -m crawler.crawl_99 --osm "Tijuca, Rio de Janeiro, BR" --step 1.5 --delay 90 --resume
```

**Caixa de coordenadas (bounding box) custom:**
```powershell
python -m crawler.crawl_99 --bbox=-22.94,-22.91,-43.26,-43.21 --step 1.5 --delay 90
```

> Comece sempre com `--max-points 3 --dry-run` pra validar antes de soltar a grade toda.

---

## 5. MODO INTERATIVO (menu) — sem decorar comandos

Rode **sem nenhuma flag** e o crawler abre um menu perguntando tudo:
```powershell
python -m crawler.crawl_99
```
```
Escolha o modo:
  1) Fila de endereços (arquivo txt)
  2) Cidade pré-definida
  3) Bounding box
  4) Bairro/área (OSM)
> 1
Arquivo da fila [crawler/queue.txt]: _
Delay entre pontos (s) [60]: _
Retomar de onde parou? (S/n): _
Dry-run (não envia ao Tinybird)? (s/N): _
Máx. de pontos (0 = todos): _
```
(Se você passar qualquer flag de modo, o menu é pulado — bom pra automação.)

---

## 6. Flags úteis (resumo)

| Flag | Pra quê |
|---|---|
| `--queue <arquivo>` | modo fila (lista de coords) |
| `--city` / `--osm` / `--bbox` | modo área (grade) |
| `--step <km>` | espaçamento da grade (modo área) |
| `--delay <s>` | **pausa entre pontos — use ≥ 60-90s contra o rate limit** |
| `--resume` | retoma de onde parou (pula pontos já batidos) |
| `--max-points <n>` | limita a quantidade de pontos (bom pra testar) |
| `--dry-run` | captura mas **não envia** ao Tinybird (preview) |
| `--cycles` / `--swipes` | profundidade do scroll por ponto (padrão 8/6) |

---

## 7. Onde ficam os resultados

- **`restaurantes.json`** / **`restaurantes_full.json`** — lojas do último ponto capturado.
- **Tinybird** — cada ponto envia o feed (event_type `app_request`); confira no Grafana.
- **`crawler/state/seen.json`** — todos os `shopId` já vistos (dedup global).
- **`crawler/state/<fila>.done`** — coordenadas já batidas da fila (pro `--resume`).

---

## 8. Dicas e problemas comuns

**Rate limit do 99** ("Muitas operações seguidas. Faça uma pausa" / "Você está desconectado"):
- É o 99 te limitando por muitas ações seguidas. **Aumente o `--delay`** (90-120s+), rode
  **menos pontos por vez** (`--max-points`), e **espere** (minutos a horas) antes de retomar.
- Pra retomar sem reprocessar: rode o mesmo comando com **`--resume`**.

**O app travou (ANR) / não responde:**
- Force-stop e retome: o crawler já faz force-stop por ponto, mas se travar no meio, é só
  rodar de novo com `--resume` (ele pula o que já foi).

**Trocar a localização do mock exige force-stop:**
- Sempre que a coordenada muda, o 99 precisa de force-stop pra pegar a nova. **O crawler já
  faz isso automaticamente** a cada ponto — você não precisa fazer nada.

**Feed não fica pronto:**
- Confira: celular logado no 99? mock ativo (`fakegps.py --check`)? `meta-overlayfs` montado?
  Frida 17.6.1 rodando?

**Validar antes de soltar tudo:**
- Sempre comece com `--max-points 1 --dry-run` pra confirmar que o fluxo está OK naquele dia.

---

## 9. Receita rápida (copia e cola)

**Escolas de um ponto → fila → bater:**
```powershell
python -m crawler.schools --point "-22.9249,-43.2326" --radius 3
python -m crawler.crawl_99 --queue crawler/queue.txt --max-points 1 --dry-run   # testa
python -m crawler.crawl_99 --queue crawler/queue.txt --delay 90 --resume        # roda
```

**Cidade inteira:**
```powershell
python -m crawler.crawl_99 --city goiania --step 4 --max-points 3 --dry-run     # testa
python -m crawler.crawl_99 --city goiania --step 4 --delay 90 --resume          # roda
```
