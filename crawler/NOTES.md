# NOTES — spike do crawler 99 Food

## Estado do device (spike 1, 2026-06-24)

- Device `ZF524JQN43` conectado, root OK, SELinux permissive.
- **fakegps.py validado parcialmente**: o encoder do DataStore protobuf reproduz
  byte-a-byte o arquivo original; `set_location`/`--show` gravam e leem corretamente
  `/data/data/com.noobexon.xposedfakelocation/files/datastore/xposed_shared_prefs.preferences_pb`.
  - ⚠️ Pendência: `cp` como root deixa o arquivo `root:root`; o `chown 10381:10381`
    deu "Permission denied" (toybox). Como o módulo LSPosed lê esse arquivo de DENTRO
    do com.taxis99 (uid != 10381), provavelmente precisa ser legível pelo módulo →
    avaliar `chown` correto OU tornar legível (perm/owner) sob SELinux permissive.
    Não dá pra concluir enquanto o app estiver deslogado (ver bloqueio).

## BLOQUEIO: app 99 está DESLOGADO

- Ao relançar `com.taxis99`: aparece overlay de login ("Fazer login de outra forma",
  "Entrar com Google/Facebook", telefone +55) e, na home, o feed mostra
  **"Você está desconectado. Inicie sua sessão"** + "Tentar novamente".
- `customer_tv_home_address` vazio (sem endereço). Tocar na área de endereço não abre o
  seletor — exige sessão.
- `probe_loc.js` (hook em `Location.getLatitude/getLongitude`) NÃO capturou nenhuma
  leitura → o app nem tenta ler localização sem login.
- **Consequência**: sem login não há feed, não há como setar endereço, e não dá pra
  validar a propagação do mock end-to-end. É pré-requisito (igual ao scraper atual).

## Frida: versão do PC incompatível

- `frida --version` no PC = **17.9.1**. README exige **17.6.1** (17.9.x é detectado e
  mata o app ~1 min). O attach do spike funcionou por segundos, mas captura estável
  precisa de 17.6.1 → rodar `setup.ps1` ou `pip install --force-reinstall --no-deps frida==17.6.1`.

## Resource-ids reais descobertos (home, MainActivityImplV2) — p/ screen.py

- Feed (RecyclerView): `customer_rv_home_main`  (e `customer_fl_home_feed_container`)
- Endereço: `customer_tv_home_address` (texto), área clicável `customer_rl_home_feed_address`
- Busca: `customer_ll_home_search` / hint `customer_tv_home_search_hint` ("Encontre restaurantes e pratos")
- Estado vazio/erro: `customer_abnormal_layout` + texto "Você está desconectado" + botão `go_button_text` ("Tentar novamente")
- "Sem endereço": `customer_fl_no_address_container`
- Nav inferior: tabs "Corrida" / centro (lottie) / "Entrega" / "Pay"  (Food = item central `select_lottie`?)
- Overlay de login dismissável: botão content-desc "Dispensar" e "Fechar página"

## CAUSA RAIZ do mock não funcionar (confirmada 2026-06-24)

- App FakeLocation abre com diálogo **"Module Not Active — XposedFakeLocation module is
  not active in your Xposed manager app."**
- LSPosed db `/data/adb/lspd/config/modules_config.db`:
  - `modules_state`: `com.noobexon.xposedfakelocation` → **enabled=1** (ligado).
  - `scope`: **ZERO linhas** pro módulo → **escopo VAZIO**.
- LSPosed só injeta o módulo nos apps do escopo. Escopo vazio → não carrega em nenhum
  app (nem no próprio FakeLocation, nem no com.taxis99). Por isso:
  - O mock nunca se aplica.
  - As leituras `-22.93 provider=network` eram a **localização REAL** do device (Rio/Tijuca),
    não o mock (que estava em Rio -22.92108 com is_playing=false de qualquer forma).
- **Escrita direta no datastore é irrelevante enquanto o módulo não estiver no escopo.**
- O módulo NÃO tem intent/broadcast exportado (só MainActivity = mapa). Controle = UI/DataStore.
- Tela de endereço do 99 ("Usar minha localização" / refresh) é **WebView** → não legível por
  uiautomator → precisa de tap por coordenada (screenshot).
- O feed da home usa o **endereço salvo (poiId)**, não GPS ao vivo → mudar GPS exige
  re-resolver "Usar minha localização" por ponto (ou trocar endereço no seletor).

## CORREÇÃO necessária (ação do usuário no LSPosed Manager)

1. LSPosed Manager → Módulos → XposedFakeLocation → **definir Escopo**: marcar
   **99 (com.taxis99)** e **XposedFakeLocation** (e opcional: System Framework p/ providers).
2. Force-stop `com.taxis99` e reabrir (ou reboot).
3. Abrir o app FakeLocation → não deve mais dizer "Module Not Active"; setar ponto + Play.
4. Re-rodar o spike: com escopo OK, testar se mock propaga (file-write@start OU UI) e como
   o feed segue (relaunch + "usar localização atual").

## Spike 2 (após usuário "ativar" o módulo) — mock ATIVO no app dele, mas NÃO no 99

- App FakeLocation agora abre normal (mapa + Play); ao escrever o datastore com o app
  PARADO e depois abri-lo, ele entra em **playing** (botão vira STOP) em SP → mock ativo
  no processo do próprio FakeLocation. ✅ Mecanismo de set por arquivo (stop→write→open) OK.
- PORÉM o **com.taxis99 continua lendo GPS REAL**: probe `Location.getLatitude` capturou
  `-22.9317, -43.2456 provider=gps` (e antes `provider=network`) — Rio real, não SP.
- Ou seja: o módulo injeta no app dele, mas **não no com.taxis99**.
  Causas prováveis: (a) com.taxis99 não está marcado no **escopo** do módulo; e/ou
  (b) mudança de escopo do LSPosed só aplica de verdade após **reboot**.
- Tentar tornar o datastore legível por todos falhou: `chmod` como root deu
  **"Operation not permitted"** e `ls` "Permission denied" → **SUSFS** protege o path
  (intermitente; `cp/chown/chmod 600` do fakegps funcionam, mas chmod 644 não).
- DB do LSPosed (mesmo pareando WAL) não mostra com.taxis99 no scope → reforça (a).

### Conclusão do spike (mock)
O caminho de SET da coord é o **fakegps (stop→write→open FakeLocation)** — validado.
Falta o módulo efetivamente injetar no com.taxis99: **marcar com.taxis99 no escopo +
REBOOT**. Sem isso, nenhum método (file nem UI) muda a localização do 99.

## Spike 3 (pós-reboot) — mock SET ok, mas 99 ainda lê REAL; app tem anti-tamper

- Pós-reboot: FakeLocation entra em playing (STOP) em SP ✅ (set via stop→write→open OK).
- Mas o 99 "Usar minha localização" / tela de pin do mapa continua resolvendo
  **"Rua João Alfredo, Tijuca/Rio"** (real) — mock NÃO chega no com.taxis99.
- 99 usa **GMS FusedLocationProviderClient** (perms FINE/COARSE; com.google.android.gms
  presente). Para fakear fused, o módulo normalmente precisa de **Google Play Services
  (com.google.android.gms)** e/ou **System Framework (android)** no ESCOPO — não só o app.
- LSPosed logs (`/data/adb/lspd/log/verbose_*.log`): com.taxis99 **crasha repetidamente**
  sob frida — `SIGABRT/SIGSEGV`, `xcrash`, `com.didichuxing.mas.sdk.quality`,
  `SuspendThreadByPeer timed out`. = anti-tamper da DiDi reagindo à instrumentação.
  → probes longos derrubam o app; capturas devem ser injeções CURTAS (como o heap-scan).
- Verificação por hook getLatitude é não-confiável (GMS fused + reverse-geocode server-side
  + anti-tamper). Verificação boa = VISUAL ("Usar minha localização" mostra a cidade mockada).

### Ação do usuário (próximo destravamento)
No LSPosed Manager, no escopo do XposedFakeLocation, MARCAR:
  - 99 (com.taxis99)
  - **Google Play Services (com.google.android.gms)**  ← provável peça que falta (fused)
  - **System Framework / Android (android)**
  - o próprio XposedFakeLocation
Depois **reboot** e verificar visualmente no 99.

## Spike 4 (pós-reboot + UI Play) — mock AINDA não chega no 99 (escopo)

- Flow do usuário confirmado: mudar coords → force-stop do app alvo → módulo em PLAY
  (o Play pela UI/FAB importa, não só o is_playing no arquivo). FAB do FakeLocation em (911,2097).
- Mesmo seguindo o flow (set SP → FakeLocation Play via FAB → force-stop 99 → relaunch):
  o pin/"Usar minha localização" do 99 resolveu "R. Silva Teles, Andaraí, **Rio**"
  (~2km de Tijuca; drift do GPS real), NÃO São Paulo. = mock NÃO injeta no com.taxis99.
- Não consigo ler/editar o escopo via db: `cp/cat` do `modules_config.db-wal/-shm` dá
  **Permission denied** intermitente (SUSFS). O db principal legível tem scope p/ outros
  módulos mas ZERO p/ fakelocation (as entradas do usuário estão no WAL protegido).
- Coords úteis do 99 (device 1080x2400) p/ screen.py: endereço (388,217); refresh
  "Usar minha localização" (949,657); linha p/ mapa de pin (300,657); "Confirmar local"
  (539,2212). Telas de endereço/mapa/cupons são WebView → coords por screenshot, não uiautomator.

### BLOQUEIO RESTANTE (ação do usuário, UI do LSPosed — não dá pra fazer via db por SUSFS)
No LSPosed Manager → XposedFakeLocation → Escopo, garantir CHECADOS:
  - **99 (com.taxis99)**
  - **Google Play Services (com.google.android.gms)** — o 99 usa fused/GMS; sem GMS no
    escopo o app pega localização real. (Pra aparecer: menu ⋮ → "Mostrar apps do sistema".)
  - System Framework (android), e o próprio XposedFakeLocation.
Depois reboot e re-testar (set SP via fakegps + Play + force-stop 99 + relaunch →
"Usar minha localização" deve virar São Paulo).

## RESOLUÇÃO do mock (pesquisa web, 2026-06-25) — controle por BROADCAST

- A v0.0.6 instalada **só seta localização por toque no mapa**; o DataStore
  (`last_clicked_location`) é a coord, mas o serviço em execução cacheia e ignora
  escritas no arquivo → por isso file-write/FAB não trocavam a coord de forma confiável.
- **A partir da v0.0.9** o módulo tem **controle externo por broadcast (headless)**:
  `ControlReceiver` + `am broadcast` pra setar lat/lng e start/stop SEM UI.
  (docs/EXTERNAL_CONTROL.md, repo noobexon1/XposedFakeLocation; latest = v0.1.2.)
- Comandos (após ligar Settings → External Control → "Allow external broadcast control"):
  ```
  am broadcast -a com.noobexon.xposedfakelocation.action.SET_LOCATION \
    -n com.noobexon.xposedfakelocation/.manager.control.ControlReceiver \
    --ed latitude <LAT> --ed longitude <LNG> --ez start true
  am broadcast -a com.noobexon.xposedfakelocation.action.STOP \
    -n com.noobexon.xposedfakelocation/.manager.control.ControlReceiver
  ```
- `fakegps.py` reescrito p/ usar broadcast (set_location/activate/stop); `--check`
  detecta se o ControlReceiver existe. As funções DataStore/FAB viraram `_legacy_*`.
- **AÇÃO DO USUÁRIO**: atualizar XposedFakeLocation p/ **v0.1.2**; ligar "Allow external
  broadcast control"; em Target Apps marcar com.taxis99 + "Enable system-level hooks"
  (cobre GMS/fused); reabrir o 99. Depois `python crawler/fakegps.py --check` deve dar True.
- Verificação confiável do mock = o pin "Usar minha localização" do 99 (provado que reflete
  o GPS ao vivo, ignora o endereço salvo). Device fica em RETRATO travado (FakeLocation força
  paisagem; lock evita bagunçar coords do 99).

## SOLUÇÃO em andamento: Frida no system_server (2026-06-25)

Por que: o 99 lê localização por caminho NATIVO (provado: 3 hooks Frida abrangentes no
processo do 99 — android.location, GMS fused, NMEA/GNSS — ZERO chamadas). Só **system-level**
cobre. Vector v2.0 (LSPosed moderno, API 101) **não carrega** no zygisksu 1.3.4 do device
(sem injeção/companion) → revertido pro LSPosed IT (que voltou OK: lspd + companion rodando).

Caminho escolhido: **Frida hookando o system_server** (frida ANEXA no system_server OK).
Pontos de hook corretos (espelhados do XposedFakeLocation SystemServicesHooks.kt, que JÁ
funcionou no device em modo system-level):
  - `com.android.server.location.LocationManagerService.getLastLocation`  → retorna FAKE  ← APP-FACING (o que faltava)
  - `LocationManagerService.getCurrentLocation`                            → bloqueia
  - GNSS bruto (registerGnssStatusCallback/registerGnssNmeaCallback/addGnssMeasurementsListener/...) → bloqueia
  - `com.android.server.location.provider.LocationProviderManager.onReportLocation` → reescreve Location
ERRO anterior: hookei só `LocationProviderManager.getLastLocationUnsafe`/`onReportLocation`
(camada interna) → não disparava. O certo é `LocationManagerService.getLastLocation` (Binder app-facing).

Implementado em `crawler/ss_mock.js` (lê coords de `/data/local/tmp/fakeloc.txt` = "lat,lng";
system_server CONSEGUE ler — DIAG confirmou). Uso:
  adb shell "echo '<lat>,<lng>' > /data/local/tmp/fakeloc.txt; chmod 644 ..."
  SS=$(adb shell pidof system_server); frida -H 127.0.0.1:2222 -q -p $SS -l crawler/ss_mock.js  (residente)
Verificação: Google Maps (bolinha em SP) é indicador limpo. NÃO usar sdk_sharedpreference do
99 (é endereço salvo/servidor, não GPS ao vivo — sempre -22.9312591).

PENDENTE: testar o ss_mock.js corrigido (LMS.getLastLocation) — USB caiu antes de validar.
Ao retomar: re-subir fserver/forward, escrever fakeloc.txt=SP, anexar ss_mock.js no
system_server (residente na MESMA chamada), abrir Maps → confirmar bolinha em SP; depois 99.

Estado do device a restaurar p/ uso normal: XFL no LSPosed IT precisa ser re-habilitado no
manager (a config churnou). O Vector foi removido. fakeloc.txt fica em /data/local/tmp.

## Próximos passos (após login)

1. Logar no app + garantir que carrega o feed em algum endereço.
2. Re-rodar spike: `fakegps.set_location` distante → relaunch → tocar endereço →
   "usar localização atual" → ver se resolve no ponto falso (valida mock + modo do feed).
3. Resolver perm/owner do datastore se a propagação por arquivo falhar (fallback: UI do FakeLocation).
</content>
