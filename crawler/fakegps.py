#!/usr/bin/env python3
"""
fakegps.py — setter de mock GPS do crawler 99 Food.

Controla o modulo LSPosed XposedFakeLocation (com.noobexon.xposedfakelocation) pela
API de CONTROLE EXTERNO por broadcast (headless), disponivel a partir da v0.0.9 do modulo
(ver docs/EXTERNAL_CONTROL.md no repo noobexon1/XposedFakeLocation). Setamos lat/lng e
ligamos/desligamos o mock via `adb am broadcast` — sem tocar na UI, sem hack de arquivo.

PRE-REQUISITOS (uma vez, no app XposedFakeLocation >= v0.1.2):
  - Settings -> External Control -> "Allow external broadcast control" LIGADO.
  - Target Apps -> com.taxis99 marcado; "Enable system-level hooks" LIGADO (cobre GMS/fused).

Uso (standalone):
  python fakegps.py <lat> <lng>      # seta e liga o mock no ponto
  python fakegps.py --stop           # desliga o mock
  python fakegps.py --check          # testa se o ControlReceiver existe (versao c/ headless)

Obs: a versao ANTIGA (0.0.6) NAO tem o ControlReceiver -> setava localizacao so por
toque no mapa. As funcoes _push_pb/encode_preferences/activate (DataStore) ficam abaixo
como FALLBACK historico, mas o caminho oficial agora e' o broadcast.
"""
import subprocess
import sys
import tempfile
import os

PKG_FAKE = "com.noobexon.xposedfakelocation"
RECEIVER = f"{PKG_FAKE}/.manager.control.ControlReceiver"
ACTION_SET = f"{PKG_FAKE}.action.SET_LOCATION"
ACTION_START = f"{PKG_FAKE}.action.START"
ACTION_STOP = f"{PKG_FAKE}.action.STOP"
DS_DIR = f"/data/data/{PKG_FAKE}/files/datastore"
DS_PATH = f"{DS_DIR}/xposed_shared_prefs.preferences_pb"
SDCARD_TMP = "/sdcard/_fg_push.pb"


def _adb(args, **kw):
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


# ---- API oficial: controle por broadcast (headless, modulo >= v0.0.9) --------

def _broadcast(action, extras=None):
    args = ["shell", "am", "broadcast", "-a", action, "-n", RECEIVER]
    for k, v in (extras or {}).items():
        flag, val = v
        args += [flag, k, val]
    r = _adb(args)
    return r.stdout + r.stderr


def set_location(lat, lng, start=True):
    """Seta lat/lng e (por padrao) liga o mock — via broadcast SET_LOCATION."""
    return _broadcast(ACTION_SET, {
        "latitude": ("--ed", str(lat)),
        "longitude": ("--ed", str(lng)),
        "start": ("--ez", "true" if start else "false"),
    })


def activate(lat, lng):
    """Compat: seta o ponto e liga o mock (broadcast)."""
    return set_location(lat, lng, start=True)


def stop():
    """Desliga o mock — via broadcast STOP."""
    return _broadcast(ACTION_STOP)


def has_control_receiver():
    """True se o app instalado tem o ControlReceiver (versao com headless)."""
    out = _adb(["shell", "pm", "dump", PKG_FAKE]).stdout or ""
    return "ControlReceiver" in out


# ---- FALLBACK historico: escrita no DataStore (versao antiga, so toque no mapa) ----

def _su(cmd):
    return _adb(["shell", "su", "-c", cmd])


def _su(cmd):
    """Roda um comando shell como root no device."""
    return _adb(["shell", "su", "-c", cmd])


def _fake_uid():
    """uid numerico do app de mock (p/ chown apos o push)."""
    r = _su(f"stat -c %u /data/data/{PKG_FAKE}")
    uid = (r.stdout or "").strip()
    return uid if uid.isdigit() else "10381"


# ---- encoding do PreferenceMap (so os 2 campos que o modulo usa) -------------

def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _len_field(field_no, payload):
    """field_no com wire type 2 (LEN) + payload."""
    tag = (field_no << 3) | 2
    return bytes([tag]) + _varint(len(payload)) + payload


def _entry(key, value_msg):
    """Uma entrada do map<string,Value>: field1=key (string), field2=value (msg)."""
    body = _len_field(1, key.encode("utf-8")) + _len_field(2, value_msg)
    return _len_field(1, body)  # cada entrada e' field 1 (repeated) do PreferenceMap


def encode_preferences(lat, lng, playing):
    """Bytes do .preferences_pb com a localizacao e o estado de play."""
    loc_json = '{"latitude":%s,"longitude":%s}' % (_fmt(lat), _fmt(lng))
    # Value.string = field 5 (wire 2)
    loc_value = _len_field(5, loc_json.encode("utf-8"))
    # Value.boolean = field 1 (wire 0/varint)
    play_value = bytes([(1 << 3) | 0]) + _varint(1 if playing else 0)
    return _entry("last_clicked_location", loc_value) + _entry("is_playing", play_value)


def _fmt(x):
    """Formata coord sem zeros/notacao cientifica estranha (igual ao app)."""
    s = repr(float(x))
    return s


# ---- push para o device ------------------------------------------------------

def _push_pb(data):
    fd, tmp = tempfile.mkstemp(suffix=".pb")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        _adb(["push", tmp, SDCARD_TMP])
        uid = _fake_uid()
        # copia para o datastore, ajusta dono/perm igual ao original (600 do uid do app)
        _su(f"cp {SDCARD_TMP} {DS_PATH} && chown {uid}:{uid} {DS_PATH} && chmod 600 {DS_PATH}")
        _su(f"rm -f {SDCARD_TMP}")
    finally:
        os.unlink(tmp)


def _legacy_set_location(lat, lng, playing=True):
    """[FALLBACK v0.0.x] Seta as coords escrevendo o DataStore (so toque-no-mapa funcionava)."""
    _push_pb(encode_preferences(lat, lng, playing))


# FAB Play/Stop do app FakeLocation (ratio calibrado em 1080x2400 ~ 911,2097)
FAB_PLAY = (0.843, 0.874)


def _legacy_activate(lat, lng):
    """[FALLBACK v0.0.x] Flow por UI (descoberto no spike, frágil):
    força-parada do FakeLocation -> escreve coords+playing -> abre o app ->
    toca o FAB pra (re)iniciar o serviço de mock. O Play pela UI importa: só o
    is_playing no arquivo nao inicia o servico de injecao.
    """
    import time
    _adb(["shell", "am", "force-stop", PKG_FAKE])
    time.sleep(1)
    # escreve coords com playing=FALSE: o app abre mostrando PLAY (mock desligado),
    # e o tap no FAB INICIA o servico (Play). Se gravasse playing=true, o app abriria
    # em STOP e o tap desligaria o mock.
    _push_pb(encode_preferences(lat, lng, False))
    _adb(["shell", "monkey", "-p", PKG_FAKE, "-c", "android.intent.category.LAUNCHER", "1"])
    time.sleep(3)
    w, h = _screen_size()
    _adb(["shell", "input", "tap", str(int(FAB_PLAY[0] * w)), str(int(FAB_PLAY[1] * h))])
    time.sleep(2)


def _screen_size():
    out = _adb(["shell", "wm", "size"]).stdout or ""
    import re
    m = re.search(r"(\d+)x(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)


# ---- leitura/debug -----------------------------------------------------------

def show(silent=False):
    """Le o pb atual do device e devolve (lat, lng, playing)."""
    import re
    _su(f"cp {DS_PATH} {SDCARD_TMP} && chmod 644 {SDCARD_TMP}")
    fd, tmp = tempfile.mkstemp(suffix=".pb")
    os.close(fd)
    try:
        _adb(["pull", SDCARD_TMP, tmp])
        _su(f"rm -f {SDCARD_TMP}")
        raw = open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
    text = raw.decode("latin-1")
    m = re.search(r'\{"latitude":(-?\d+\.?\d*),"longitude":(-?\d+\.?\d*)\}', text)
    lat = float(m.group(1)) if m else None
    lng = float(m.group(2)) if m else None
    # is_playing: ...is_playing\x12\x02\x08<00|01>
    pm = re.search(rb"is_playing\x12\x02\x08([\x00\x01])", raw)
    playing = bool(pm.group(1)[0]) if pm else None
    if not silent:
        print(f"lat={lat} lng={lng} playing={playing}")
    return lat, lng, playing


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--stop":
        print(stop() or "[fakegps] STOP enviado")
    elif len(sys.argv) >= 2 and sys.argv[1] == "--check":
        ok = has_control_receiver()
        print(f"ControlReceiver presente: {ok}  "
              + ("(headless OK)" if ok else "(versao antiga sem broadcast -> atualizar p/ >= v0.0.9)"))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--show":
        show()
    elif len(sys.argv) >= 3:
        lat, lng = float(sys.argv[1]), float(sys.argv[2])
        out = set_location(lat, lng)
        print(f"[fakegps] SET_LOCATION lat={lat} lng={lng} start=true -> {out.strip()}")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
