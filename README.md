# 99 Food Scraper — extração do feed de restaurantes (`com.taxis99`)

Captura a lista de restaurantes do **99 Food / DiDi Food** lendo o objeto **já parseado da memória do app** via **Frida (heap scan)**, e exporta um `restaurantes.json`.

Este método **fura todas as camadas de proteção** do app **sem precisar quebrar a rede**:
não usa proxy, não usa SSL unpinning, não depende de QUIC/Cronet, não lê disco.
Ele pega o objeto `HomeFeedEntity` **depois** de o app baixar e decodificar a resposta.

> ⚠️ **Uso responsável.** Ferramenta de pesquisa/engenharia reversa para fins educacionais e de
> análise de dados públicos (cardápios e lojas já exibidos no próprio app). Use **apenas em
> dispositivos e contas seus**, respeite os Termos de Uso da plataforma e a LGPD. Não use para
> sobrecarregar serviços nem para coletar dados pessoais de terceiros.

---

## Índice

1. [TL;DR](#tldr)
2. [Como funciona (e por que ler da heap)](#como-funciona-e-por-que-ler-da-heap)
3. [Pré-requisitos](#pré-requisitos)
4. [Passo 1 — Setup (primeira vez)](#passo-1--setup-primeira-vez)
5. [Passo 2 — Uso (toda vez)](#passo-2--uso-toda-vez)
6. [Saída](#saída)
7. [Como funciona por dentro (deep-dive)](#como-funciona-por-dentro-deep-dive)
8. [Escalar para a cidade inteira](#escalar-para-a-cidade-inteira)
9. [Troubleshooting](#troubleshooting)
10. [Arquivos do toolkit](#arquivos-do-toolkit)
11. [Notas técnicas](#notas-técnicas)

---

## TL;DR

```powershell
# 1x (primeira vez) — instala o frida-server no device e alinha o frida do PC
.\setup.ps1

# toda vez:  abra o app 99 -> aba COMIDA (lista de restaurantes) -> depois:
.\scrape.ps1                 # ~8 ciclos de scroll + heap-scan
# saída:  restaurantes.json   e   restaurantes_full.json
```

Fluxo em uma frase: **o app baixa e decodifica o feed → o Frida lê o objeto pronto da memória → o Python consolida em JSON.**

```
 ┌─────────────┐   scroll/scan   ┌──────────────┐   pull    ┌────────────────┐   consolida   ┌────────────────────┐
 │  App 99      │ ──────────────▶ │  hook_feed.js │ ────────▶ │ heap_all.jsonl  │ ────────────▶ │ restaurantes.json   │
 │ (heap viva)  │   (Frida)       │  (Java.choose)│  (adb)    │ (1 entidade/lin)│  (consolidate)│ restaurantes_full.. │
 └─────────────┘                 └──────────────┘           └────────────────┘               └────────────────────┘
```

---

## Como funciona (e por que ler da heap)

Tentamos **tudo** de captura de rede e falhou — porque o app é blindado em camadas:

| Camada do app | Por que bloqueia a captura de rede |
|---|---|
| **Cronet/Rabbit** (HTTP nativo do Chromium) | Ignora o proxy de sistema do Android e **não usa o `connect()` do libc** (usa syscall direto) → escapa de proxy e de hook de socket. |
| **QUIC / HTTP3** | O feed sai por UDP/QUIC → não decodifica no mitmproxy; bloquear QUIC só faz o app falhar (downgrade). |
| **Cache** | O app serve do cache em memória (~5 s) e re-renderiza sem ir à rede. |
| **Múltiplos domínios** | Usa vários domínios (`didi-food.com`, `didiglobal.com`, `xiaojukeji.com`…). |
| **Sem persistência** | Os dados do feed **não ficam em disco** (só o bundle de código). |
| **Classloader isolado** | As classes do feed estão num *plugin framework* → `Java.use` simples falha. |
| **Anti-tamper / anti-frida** | Detecta e **mata o app** sob instrumentação. |

**A solução:** deixar o app fazer o trabalho (baixar + decodificar o feed) e **ler o objeto pronto da memória**. O `HomeFeedEntity` parseado tem tudo: `shopId`, `shopName`, nota, preço de entrega, tempo, tags, imagem, URL.

### A cadeia que quebrou as camadas

1. **Anti-tamper** → usar **Frida 17.6.1** (o 17.9.x é detectado e mata o app em ~1 min). **Esta é a peça mais crítica.**
2. **Anti-attach** → com 17.6.1, **attach** num launch normal funciona (`spawn` trava no splash — não usar).
3. **SELinux** → `setenforce 0` (permissive) é necessário pro Frida injetar (senão dá *"agent connection closed"*/timeout).
4. **Classloader isolado** → `Java.enumerateClassLoaders()` + `Java.ClassFactory.get(loader)` por loader.
5. **Pegar o dado** → `Java.choose()` acha as instâncias de `HomeFeedEntity` vivas na heap → `Gson().toJson()` → JSON cru.

---

## Pré-requisitos

### Versões testadas (use exatamente estas)

| Componente | Versão | Observação |
|---|---|---|
| **Frida (PC)** | **17.6.1** | `pip install --force-reinstall --no-deps frida==17.6.1`. **NÃO use 17.9.x** (detectado → mata o app). |
| **frida-server (device)** | **17.6.1** android-**arm64**, renomeado p/ `fserver` | baixado pelo `setup.ps1` de `github.com/frida/frida/releases`. |
| **Python** | 3.x | roda o `consolidate.py` e descompacta o frida-server (`lzma`). |
| **adb / platform-tools** | atual | precisa estar no **PATH**. |
| **App 99** | `com.taxis99` (testado v6.61.4) | logado, com **endereço de entrega** definido. |

> **Por que cliente e server precisam bater na versão?** O protocolo do Frida não é estável entre
> minor releases. Cliente 17.6.1 com server 17.9.x = falha de handshake ou comportamento errático.
> O `setup.ps1` força os dois para **17.6.1**.

### Device

- **Android arm64 com ROOT.** Testado: **Moto G54 (`cancunf`), Android 15, KernelSU.**
  - `su -c id -u` tem que retornar `0`.
  - Stack KernelSU do device de teste (presente, não necessariamente toda obrigatória): `susfs_manager`, `zygisksu`, `zygisk_lsposed`, `playintegrityfix`, `tricky_store`. **O decisivo é root + Frida 17.6.1 + SELinux permissive** — não foi preciso CA/SSL/proxy.
- **NÃO precisa**: CA do mitmproxy, módulo de unpinning, WireGuard, iptables, HideMyApplist. (Tudo isso era da era *"captura de rede"*, que não usamos mais.)
- **USB debugging** ligado e o computador autorizado (`adb devices` deve listar o aparelho como `device`, não `unauthorized`).

> ⚠️ SELinux fica **permissive** durante o uso (`setenforce 0`). Volta a *Enforcing* no reboot.
> Se o app detectar permissive no futuro, dá pra spoofar `getenforce`, mas hoje não é preciso.

---

## Passo 1 — Setup (primeira vez)

```powershell
cd "C:\Users\caique\Documents\scraper99"
.\setup.ps1
```

O `setup.ps1` faz, em ordem:

1. **Confere o device** via `adb` e a arquitetura (espera `arm64-v8a`).
2. **Confere root** (`su -c id -u` == `0`).
3. **Baixa** `frida-server-17.6.1-android-arm64.xz` das releases oficiais, **descompacta** (via `lzma` do Python) para o binário `fserver`.
4. **Instala** o `fserver` em `/data/local/tmp/fserver` e dá `chmod 755`.
   - É **renomeado de propósito**: o anti-tamper procura o processo chamado *"frida-server"*.
5. **Alinha o Frida do PC** para **17.6.1** (`pip install --force-reinstall --no-deps frida==17.6.1`).
6. **Testa a conexão**: sobe o `fserver`, faz `adb forward tcp:2222`, e roda `frida-ps -H 127.0.0.1:2222`.

### Saída esperada (sucesso)

```
[*] Device OK | ABI = arm64-v8a
[+] Root OK
[*] Baixando frida-server 17.6.1 (android-arm64)...
[+] Baixado (15.x MB)
[*] Descompactando (.xz -> fserver)...
[+] fserver pronto
[*] Instalando fserver em /data/local/tmp/ ...
[+] fserver instalado no device
[+] frida PC = 17.6.1
[*] Testando fserver + conexao frida...
[+] frida conecta no device (porta 2222). SETUP COMPLETO.
```

Se algo falhar aqui, **resolva antes de seguir** — veja [Troubleshooting](#troubleshooting).

---

## Passo 2 — Uso (toda vez)

1. **No celular:** abra o app **99**, faça login se preciso, **defina um endereço de entrega** e vá para a aba **Comida** (a lista de restaurantes precisa estar **na tela**).
2. **No PC:**

```powershell
.\scrape.ps1
# mais agressivo (mais lojas):
.\scrape.ps1 -Cycles 15 -SwipesPerCycle 8
```

O `scrape.ps1` faz, automaticamente:

1. `setenforce 0` (permissive) — necessário pro Frida injetar.
2. Sobe o `fserver` na porta `2222` (se não estiver no ar) + `adb forward tcp:2222`.
3. Acha o **PID** do app (abre o app se não estiver rodando) e garante a aba **Comida**.
4. **Loop**: rola a lista (`adb input swipe`) + injeta `hook_feed.js` (heap scan) → acumula as páginas vivas em `heap_all.jsonl` no device. Cada scroll carrega mais páginas; cada scan pega as que estão vivas na memória naquele instante.
5. Puxa (`adb pull`) o `heap_all.jsonl` e roda `consolidate.py`.

### Saída esperada (durante o run)

```
[*] SELinux = Permissive
[*] frida CLI = 17.6.1  (esperado 17.6.1)
[*] App com.taxis99 pid=12345
[*] Indo para a aba Comida...
[*] Loop: 8 ciclos x 6 swipes (role a lista do Food)...
    ciclo 1/8 -> 4 entidades acumuladas
    ciclo 2/8 -> 9 entidades acumuladas
    ...
TOTAL restaurantes unicos (shopId): 118
  -> restaurantes.json      (limpo)
  -> restaurantes_full.json (cru, todos os campos)
[*] PRONTO -> ...\restaurantes.json  e  restaurantes_full.json
```

### Parâmetros

| Flag | Default | O que faz |
|---|---|---|
| `-Cycles` | `8` | quantas rodadas de (scroll + scan). Mais = mais cobertura. |
| `-SwipesPerCycle` | `6` | swipes por rodada (quão fundo rola antes de cada scan). |
| `-ScanSeconds` | `10` | tempo que o Frida fica injetado por scan. |

> **Dica de cobertura:** o feed pagina conforme você rola. Se vier pouca loja, aumente
> `-Cycles`/`-SwipesPerCycle`. Cada ciclo é independente — o `heap_all.jsonl` só **acumula**
> (append), e a dedup final é por `shopId`.

---

## Saída

- **`restaurantes.json`** — limpo, um objeto por loja:

```json
{
  "shopId": "5764609582476037603",
  "nome": "Padaria Lamego - Vila Isabel",
  "nota": "4,7",
  "avaliacoes": "1000+",
  "categoria": "Padaria",
  "entrega_min": 26,
  "frete": "Gratis",
  "businessType": 1,
  "url": "...",
  "shopImg": "..."
}
```

- **`restaurantes_full.json`** — objeto **cru** de cada loja (todos os campos da API: `rating`, `fulfillment`, `tags`, `deliveryType`, `cShopStatus`, `bookableV2`, etc.).

**Dedup é por `shopId`.** Os dois arquivos versionados no repo são **exemplos reais** de saída — sobrescreva-os rodando o scraper.

---

## Como funciona por dentro (deep-dive)

### `hook_feed.js` (o coração)

```js
// 1) Enumera TODOS os classloaders (a DiDi usa plugin framework isolado)
Java.enumerateClassLoaders({
  onMatch: function (loader) {
    var f = Java.ClassFactory.get(loader);     // ClassFactory por loader
    var gson = f.use('com.google.gson.Gson').$new();
    ENT.forEach(function (cn) {                  // classes-alvo do feed
      f.use(cn);                                 // este loader tem a classe?
      f.choose(cn, {                             // acha instâncias VIVAS na heap
        onMatch: function (inst) {
          var j = gson.toJson(inst);             // serializa o objeto pronto
          if (j.indexOf('shopId') >= 0) append(j); // só feeds com lojas
        }
      });
    });
  }
});
```

Pontos-chave:
- **Por que enumerar classloaders?** As entidades do feed não estão no classloader principal do app — estão num *plugin framework* da DiDi. `Java.use('...')` direto falha; é preciso obter a `ClassFactory` **de cada loader** e perguntar "você tem essa classe?".
- **Por que `Java.choose`?** Não dá pra hookar a rede (Cronet/QUIC). Em vez disso, varremos a heap por **instâncias já existentes** de `HomeFeedEntity` — o objeto que o app montou após decodificar a resposta.
- **Por que reinjetar a cada ciclo?** O script roda **na injeção** (não fica residente). Cada injeção captura o estado atual da memória. Rolando entre injeções, novas páginas entram na heap e são capturadas no scan seguinte.
- **Filtro `length > 100 && indexOf('shopId')`**: descarta entidades vazias/parciais.

Classes-alvo (`ENT[]`):
```
com.didi.soda.customer.foundation.rpc.entity.topgun.HomeFeedEntity
com.didi.soda.customer.foundation.rpc.entity.topgun.HomeModuleEntity
com.didi.soda.customer.foundation.rpc.entity.topgun.FeedEntity
com.didi.soda.customer.foundation.rpc.entity.ModuleEntity
```

### `consolidate.py` (o parser)

- Lê `heap_all.jsonl` (1 entidade JSON por linha).
- **`walk()`** desce recursivamente em qualquer dict/list e detecta lojas pelo par `shopId` + `shopName`.
- **`parse_rating()`** extrai `nota`, `avaliacoes` e `categoria` do campo `rating`, que vem num
  formato de texto estilizado da DiDi (`&em#{"text":"4,7",...}&em#`).
- Conversões: `deliveryTime` (segundos) → `entrega_min` (minutos); `deliveryPriceAct`
  (centavos; `0` = Grátis) → `frete`.
- Dedup por `shopId` em dois dicionários (`shops_clean`, `shops_full`).

---

## Escalar para a cidade inteira

O feed de **um ponto** traz as lojas com entrega para aquele endereço (~100–130). Para cobrir uma cidade:

1. **Variar a localização** (GPS mock — ex.: *Xposed FakeLocation*) por uma **grade de pontos** (lat/lng).
2. Em cada ponto: mudar o endereço no app (usar *"localização atual"*) → rodar `.\scrape.ps1`.
3. **Dedup global por `shopId`** entre todos os pontos.

Espaçamento da grade ≈ raio de entrega (~2–3 km) para não deixar buraco. *(A automação da grade não está incluída aqui — é o próximo passo.)*

### Cardápio de cada loja

`restaurantes_full.json` traz `shopId` e `url` de cada loja. Para o cardápio, entre na loja no app e use o **mesmo método de heap scan** (as entidades de item/menu também ficam na memória) — basta estender o array `ENT[]` no `hook_feed.js` com as classes de item.

---

## Troubleshooting

| Sintoma | Causa / correção |
|---|---|
| App **morre ~1 min** após injetar | Frida errado. Use **17.6.1** (PC e device). `frida --version` deve dizer `17.6.1`. |
| `Failed to attach: agent connection closed` / `timed out` | SELinux *Enforcing*. Rode `adb shell su -c "setenforce 0"`. |
| `unable to connect to remote frida-server` | `fserver` caiu. Re-suba: `adb shell su -c "nohup /data/local/tmp/fserver -l 0.0.0.0:2222 >/dev/null 2>&1 &"` + `adb forward tcp:2222 tcp:2222`. |
| App trava no **splash** | Foi `spawn` (`-f`). **Não use spawn** — abra o app normal e use **attach** (é o que o `scrape.ps1` faz). |
| `heap_all.jsonl` vazio / 0 entidades | O app não está na **lista de restaurantes** (aba Comida com endereço). Navegue até lá e rode de novo. |
| Poucas lojas | Aumente `-Cycles`/`-SwipesPerCycle`. O feed pagina conforme rola. |
| `adb get-state` != `device` | Device não conectado/autorizado. `adb devices`; aceite o prompt de USB debugging no celular. |
| `python` não encontrado / falha ao descompactar | Instale Python 3 e garanta no PATH (o setup usa `lzma` p/ o `.xz`). |
| adb cai / device offline | Instabilidade USB. Troque cabo/porta, ou `adb tcpip 5555` + `adb connect <ip>`. |
| Nomes com `?` no console | Só o terminal Windows (cp1252). O **arquivo `.json` está em UTF-8 correto**. |

---

## Arquivos do toolkit

| Arquivo | Papel |
|---|---|
| `setup.ps1` | configuração de 1ª vez (frida-server no device + frida do PC). |
| `scrape.ps1` | uso: deploy do Frida + autoscroll + heap-scan + consolida. |
| `hook_feed.js` | o hook Frida: heap scan do `HomeFeedEntity` via classloader → `heap_all.jsonl`. |
| `consolidate.py` | `heap_all.jsonl` → `restaurantes.json` + `restaurantes_full.json`. |
| `restaurantes.json` | **exemplo** de saída limpa (sobrescrito a cada run). |
| `restaurantes_full.json` | **exemplo** de saída crua (todos os campos da API). |
| `fserver` / `*.xz` | frida-server 17.6.1 — **não versionados** (gerados pelo `setup.ps1`). |
| `heap_all.jsonl` | acumulador bruto (uma entidade por linha) — **não versionado** (gerado a cada run). |

---

## Notas técnicas

- **Entidade do feed**: `com.didi.soda.customer.foundation.rpc.entity.topgun.HomeFeedEntity`
  (chaves: `hasMore`, `compList`, `filterList`, `type`). Cada `compList[i]` é uma loja com
  `shopId, shopName, rating, deliveryTime, deliveryPriceAct, tags, shopImg, url, businessType…`.
- O campo `rating` vem em formato de texto estilizado da DiDi (`&em#{"text":"4,7",...}&em#`);
  o `consolidate.py` extrai `nota`, `avaliacoes` e `categoria` dele.
- `deliveryTime` em **segundos**; `deliveryPriceAct` em **centavos** (`0` = Grátis).
- O `hook_feed.js` roda na injeção (não fica residente) — por isso o `scrape.ps1` reinjeta
  a cada ciclo, acumulando em `heap_all.jsonl` (append, uma entidade por linha).
- Porta do Frida: `2222` (device) ↔ `127.0.0.1:2222` (PC) via `adb forward`.
