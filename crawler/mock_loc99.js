// mock_loc99.js — hook Frida de localizacao p/ o 99 (com.taxis99), versao COMPLETA e
// file-driven, baseada no stack comprovado de producao (mock-lockation.js de
// ia-scripts/unpinning, ver RELEVAMIENTO_SPOOFING_UBICACION_99.md).
//
// Diferenca p/ a versao do GitHub: (1) coords lidas de arquivo (pro crawler trocar por
// ponto, sem reiniciar), (2) Location.getLatitude/getLongitude como CATCH-ALL (cobre o
// resultado do FusedLocationProviderClient, que a versao antiga so "stub-ava"),
// (3) isFromMockProvider->false (anti-deteccao), (4) isProviderEnabled->true.
//
// Stack completo (este hook é a peça central, mas precisa das outras p/ o 99 nao detectar):
//   - HideMockLocation (LSPosed) escopado no com.taxis99  -> esconde a flag de mock
//   - Lexa Fake GPS (com.lexa.fakegps) como provedor base (opcional/backup)
//
// Coords: /data/local/tmp/fakeloc.txt  ("lat,lng"). Sem arquivo => usa o default abaixo.
// Uso (spawn, p/ pegar leituras de startup):
//   frida -H 127.0.0.1:2222 -q -f com.taxis99 -l mock_loc99.js
// Ou attach + dispare uma leitura (abrir endereco -> "usar minha localizacao").
var COORD_FILE = "/data/local/tmp/fakeloc.txt";
var DEF_LAT = -23.5505, DEF_LNG = -46.6333;   // SP Praca da Se (default)

Java.perform(function () {
    function log(m) { try { console.log("[mockloc] " + m); } catch (e) {} }

    var _lat = DEF_LAT, _lng = DEF_LNG, _t = 0;
    function refresh() {
        try {
            var now = (new Date()).getTime();
            if (now - _t < 1500) return;
            _t = now;
            var F = Java.use("java.io.File").$new(COORD_FILE);
            if (!F.exists()) return;
            var BR = Java.use("java.io.BufferedReader").$new(Java.use("java.io.FileReader").$new(F));
            var line = BR.readLine(); BR.close();
            if (!line) return;
            var p = ("" + line).trim().split(",");
            var la = parseFloat(p[0]), ln = parseFloat(p[1]);
            if (!isNaN(la) && !isNaN(ln)) { _lat = la; _lng = ln; }
        } catch (e) {}
    }
    function lat() { refresh(); return _lat; }
    function lng() { refresh(); return _lng; }

    // setLocation funcional via REPL (alem do arquivo)
    try {
        globalThis.setLocation = function (a, b) {
            if (typeof a === "number") { _lat = a; _lng = b; log("setLocation -> " + a + "," + b); }
        };
    } catch (e) {}

    var JSystem = Java.use("java.lang.System");
    var SystemClock = Java.use("android.os.SystemClock");
    function stamp(loc) {
        try { loc.setAccuracy(15.0); loc.setTime(JSystem.currentTimeMillis());
              loc.setElapsedRealtimeNanos(SystemClock.elapsedRealtimeNanos()); } catch (e) {}
        try { loc.setAltitude(0.0); loc.setSpeed(0.0); loc.setBearing(0.0); } catch (e) {}
    }

    // 1) LocationManager.getLastKnownLocation -> reescreve
    try {
        var LM = Java.use("android.location.LocationManager");
        LM.getLastKnownLocation.overload("java.lang.String").implementation = function (p) {
            var loc = this.getLastKnownLocation(p);
            try {
                if (loc == null) { loc = Java.use("android.location.Location").$new(p || "gps"); }
                loc.setLatitude(lat()); loc.setLongitude(lng()); stamp(loc);
            } catch (e) {}
            return loc;
        };
        // 6) isProviderEnabled -> true p/ gps/network/passive
        LM.isProviderEnabled.overload("java.lang.String").implementation = function (p) {
            if (p === "gps" || p === "network" || p === "passive") return true;
            return this.isProviderEnabled(p);
        };
        log("LocationManager hookado");
    } catch (e) { log("LM err " + e); }

    // 2/3/4/7) Location: construtor + getters + isFromMockProvider
    try {
        var Location = Java.use("android.location.Location");
        Location.$init.overload("java.lang.String").implementation = function (p) {
            this.$init(p);
            try { this.setLatitude(lat()); this.setLongitude(lng()); stamp(this); } catch (e) {}
        };
        Location.getLatitude.implementation = function () { return lat(); };
        Location.getLongitude.implementation = function () { return lng(); };
        Location.isFromMockProvider.implementation = function () { return false; }; // anti-deteccao
        log("Location getters/isFromMockProvider hookados");
    } catch (e) { log("Location err " + e); }

    // 5) FusedLocationProviderClient — hook COMPLETO via os getters de Location (acima ja
    //    cobrem o resultado). Aqui so logamos p/ confirmar uso do fused.
    try {
        var FLPC = Java.use("com.google.android.gms.location.FusedLocationProviderClient");
        FLPC.getLastLocation.overloads.forEach(function (ov) {
            ov.implementation = function () { log("FLPC.getLastLocation (resultado coberto pelos getters)"); return ov.apply(this, arguments); };
        });
        log("FusedLocationProviderClient presente/hookado");
    } catch (e) { log("FLPC ausente: " + e); }

    // 8) LocationResult (fused live updates): reescreve as Location entregues
    try {
        var LR = Java.use("com.google.android.gms.location.LocationResult");
        LR.getLastLocation.implementation = function () {
            var loc = this.getLastLocation();
            try { if (loc) { loc.setLatitude(lat()); loc.setLongitude(lng()); stamp(loc); } } catch (e) {}
            return loc;
        };
        log("LocationResult hookado");
    } catch (e) {}

    log("INSTALADO. coords iniciais=" + lat() + "," + lng() + "  file=" + COORD_FILE);
});
