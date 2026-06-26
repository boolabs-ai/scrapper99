"""
screen.py — máquina de estados de tela do 99 Food (camada de automação do crawler).

Responsabilidade: abrir o app, DISPENSAR os anúncios/overlays de abertura, detectar
quando o FEED está pronto pra scrollar, e (por ponto) trocar a localização de entrega
via "Usar minha localização". NÃO faz captura (isso é o capture.ps1 / lado scraper).

Telas nativas (home/feed) são lidas via `uiautomator dump` (resource-ids reais
mapeados no device de teste). Telas de endereço/mapa/cupons são WebView e NÃO expõem
hierarquia → tap por coordenada (ratios calibrados em 1080x2400, ver ADDR_* abaixo).

Uso (debug):
  python -m crawler.screen ready          # garante app aberto + feed pronto
  python -m crawler.screen dismiss        # só dispensa overlays
  python -m crawler.screen set-current    # seleciona "usar minha localização" (precisa do mock OK)
"""
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = "com.taxis99"

# resource-ids reais (prefixo do app) — descobertos via dump na home logada
RID_ADDRESS   = "customer_tv_home_address"       # texto do endereço (vazio = sem endereço)
RID_FEED_RV   = "customer_rv_home_main"          # RecyclerView do feed
RID_SHOPNAME  = "customer_tv_special_shop_name"  # nome de loja (presença = feed carregado)
RID_ABNORMAL  = "customer_abnormal_layout"       # estado de erro/"desconectado"
RID_RETRY     = "go_button_text"                 # botão "Tentar novamente"
RID_NOADDR    = "customer_fl_no_address_contain" # "sem endereço"

# telas WebView (endereço/mapa) — ratios calibrados em 1080x2400
ADDR_REFRESH = (0.879, 0.274)  # ícone refresh do "Usar minha localização" (~949,657)
ADDR_ROW     = (0.278, 0.274)  # linha "Usar minha localização" -> abre mapa de pin (~300,657)
PIN_CONFIRM  = (0.499, 0.922)  # "Confirmar local de encontro" (~539,2212)

# textos/labels de botões de dispensar anúncio (content-desc/text)
DISMISS_LABELS = ["dispensar", "fechar", "pular", "agora não", "agora nao",
                  "close", "skip", "depois", "não, obrigado", "nao obrigado", "x"]


def _adb(args):
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def shell(cmd):
    return _adb(["shell", cmd]).stdout


def su(cmd):
    return _adb(["shell", "su", "-c", cmd]).stdout


def screen_size():
    out = shell("wm size")
    import re
    m = re.search(r"(\d+)x(\d+)", out or "")
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)


def tap(x, y):
    _adb(["shell", "input", "tap", str(int(x)), str(int(y))])


def tap_ratio(rx, ry):
    w, h = screen_size()
    tap(rx * w, ry * h)


def back():
    _adb(["shell", "input", "keyevent", "KEYCODE_BACK"])


def app_pid():
    return (shell(f"pidof {PKG}") or "").strip().split(" ")[0] if shell(f"pidof {PKG}").strip() else ""


def current_focus():
    out = shell("dumpsys window") or ""
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            return line.strip()
    return ""


def launch():
    _adb(["shell", "am", "force-stop", PKG])
    time.sleep(1)
    _adb(["shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1"])


def dump(retries=3):
    """uiautomator dump -> ElementTree root, ou None se for tela WebView (sem hierarquia)."""
    for _ in range(retries):
        r = _adb(["shell", "uiautomator", "dump", "/sdcard/_ui.xml"])
        if "dumped" in (r.stdout + r.stderr).lower():
            xml = _adb(["exec-out", "cat", "/sdcard/_ui.xml"]).stdout
            try:
                return ET.fromstring(xml)
            except Exception:
                pass
        time.sleep(1)
    return None


def _nodes(root):
    return root.iter("node") if root is not None else []


def find(root, rid_substr):
    for n in _nodes(root):
        if rid_substr in n.attrib.get("resource-id", ""):
            return n
    return None


def node_center(n):
    import re
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def is_disconnected(root):
    if find(root, RID_ABNORMAL) is not None or find(root, RID_RETRY) is not None:
        return True
    for n in _nodes(root):
        if "desconectado" in n.attrib.get("text", "").lower():
            return True
    return False


def feed_ready(root):
    """Feed pronto = tem endereço definido + cards de loja + não está desconectado."""
    if root is None:
        return False
    if is_disconnected(root):
        return False
    addr = find(root, RID_ADDRESS)
    addr_ok = addr is not None and len(addr.attrib.get("text", "").strip()) >= 3
    has_shops = find(root, RID_SHOPNAME) is not None or find(root, RID_FEED_RV) is not None
    return addr_ok and has_shops


def dismiss_overlays():
    """Dispensa overlays nativos (botão) e promos WebView (BACK). Retorna nº de dispensas."""
    dismissed = 0
    for _ in range(6):
        root = dump()
        if root is not None and feed_ready(root):
            break
        acted = False
        if root is not None:
            # botão de dispensar nativo (content-desc/text)
            for n in _nodes(root):
                label = (n.attrib.get("content-desc", "") + " " + n.attrib.get("text", "")).strip().lower()
                if label and any(d == label or (len(d) > 2 and d in label) for d in DISMISS_LABELS):
                    c = node_center(n)
                    if c:
                        tap(*c); dismissed += 1; acted = True; time.sleep(1.5); break
        if not acted:
            # tela WebView/promo (dump vazio ou sem botão) -> BACK costuma fechar
            foc = current_focus()
            if root is None or "WebView" in (ET.tostring(root, encoding="unicode") if root is not None else ""):
                back(); dismissed += 1; time.sleep(1.5)
            elif not feed_ready(root):
                back(); time.sleep(1.5)
        time.sleep(0.5)
    return dismissed


def wait_ready(timeout=75, relaunch=True):
    """Abre o app (se preciso) e espera o feed ficar pronto, dispensando overlays."""
    if relaunch or not app_pid():
        launch()
        time.sleep(8)
    t0 = time.time()
    while time.time() - t0 < timeout:
        root = dump()
        if root is not None and feed_ready(root):
            return True
        if root is not None and is_disconnected(root):
            # desconectado: tenta "Tentar novamente"
            btn = find(root, RID_RETRY)
            if btn:
                c = node_center(btn)
                if c:
                    tap(*c); time.sleep(4); continue
        dismiss_overlays()
        time.sleep(2)
    return False


def address_text():
    root = dump()
    n = find(root, RID_ADDRESS) if root is not None else None
    return n.attrib.get("text", "").strip() if n is not None else ""


def open_address():
    """Abre a tela 'Endereço de entrega' tocando no endereço (elemento nativo)."""
    root = dump()
    n = find(root, RID_ADDRESS) if root is not None else None
    c = node_center(n) if n is not None else None
    if c:
        tap(*c)
    else:
        tap_ratio(0.36, 0.09)  # fallback p/ a área do endereço
    time.sleep(6)


def select_current_location(confirm=True):
    """Seleciona 'Usar minha localização' (re-resolve via GPS mockado) e confirma o pin.

    PRÉ-REQUISITO: o mock GPS precisa estar ATIVO e injetando no com.taxis99
    (LSPosed scope: com.taxis99 + Google Play Services). Telas são WebView → coords.
    """
    open_address()
    tap_ratio(*ADDR_REFRESH)   # força re-resolver a localização atual
    time.sleep(8)
    tap_ratio(*ADDR_ROW)       # abre o mapa de pin no ponto atual
    time.sleep(8)
    if confirm:
        tap_ratio(*PIN_CONFIRM)  # "Confirmar local de encontro"
        time.sleep(6)
        # após confirmar costuma abrir "Informações de endereço" (número/complemento)
        # -> fluxo adicional a calibrar quando o mock estiver validado.


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ready"
    if cmd == "ready":
        ok = wait_ready()
        print("feed_ready =", ok, "| address =", repr(address_text()))
    elif cmd == "dismiss":
        print("dispensados:", dismiss_overlays(), "| address =", repr(address_text()))
    elif cmd == "addr":
        open_address(); print("abriu endereço; focus =", current_focus())
    elif cmd == "set-current":
        select_current_location()
        print("select_current_location done; address agora =", repr(address_text()))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
