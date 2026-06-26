// ss_mock.js — fake de localizacao no system_server (Android 15), pontos de hook
// espelhados do XposedFakeLocation (SystemServicesHooks.kt, que JA funcionou no device):
//   - com.android.server.location.LocationManagerService.getLastLocation  -> retorna FAKE
//   - LocationManagerService.getCurrentLocation                            -> bloqueia (default)
//   - GNSS bruto (registerGnssStatusCallback/NMEA/measurements/...)        -> bloqueia
//   - LocationProviderManager.onReportLocation                             -> reescreve p/ FAKE
// Coords de /data/local/tmp/fakeloc.txt ("lat,lng"). Sem arquivo/vazio => passa direto.
// Tudo em try/catch p/ nunca derrubar o system_server.
var COORD_FILE = "/data/local/tmp/fakeloc.txt";

Java.perform(function () {
    function log(m) { try { console.log("[ssmock] " + m); } catch (e) {} }

    var _cache = null, _t = 0;
    function coords() {
        try {
            var now = (new Date()).getTime();
            if (now - _t < 1500) return _cache;
            _t = now;
            var F = Java.use("java.io.File").$new(COORD_FILE);
            if (!F.exists()) { _cache = null; return null; }
            var BR = Java.use("java.io.BufferedReader").$new(Java.use("java.io.FileReader").$new(F));
            var line = BR.readLine(); BR.close();
            if (!line) { _cache = null; return null; }
            var p = ("" + line).trim().split(",");
            var lat = parseFloat(p[0]), lng = parseFloat(p[1]);
            if (isNaN(lat) || isNaN(lng)) { _cache = null; return null; }
            _cache = { lat: lat, lng: lng }; return _cache;
        } catch (e) { return _cache; }
    }

    var Location = Java.use("android.location.Location");
    var SystemClock = Java.use("android.os.SystemClock");
    var JSystem = Java.use("java.lang.System");
    function makeFake(orig, c) {
        try {
            var loc = (orig != null && !orig.$isNull) ? orig : Location.$new("gps");
            loc.setProvider("gps");
            loc.setLatitude(c.lat); loc.setLongitude(c.lng);
            loc.setAccuracy(15.0);
            loc.setTime(JSystem.currentTimeMillis());
            loc.setElapsedRealtimeNanos(SystemClock.elapsedRealtimeNanos());
            try { loc.setAltitude(0.0); } catch (e) {}
            try { loc.setSpeed(0.0); } catch (e) {}
            try { loc.setBearing(0.0); } catch (e) {}
            try { loc.setFromMockProvider(false); } catch (e) {}
            return loc;
        } catch (e) { return orig; }
    }

    function findClass(names) {
        for (var i = 0; i < names.length; i++) { try { return Java.use(names[i]); } catch (e) {} }
        return null;
    }
    function hookAll(C, method, impl, tag) {
        if (!C) return 0;
        try {
            var ovs = C[method].overloads; var n = 0;
            ovs.forEach(function (ov) { try { ov.implementation = impl(ov); n++; } catch (e) {} });
            if (n) log("hooked " + tag + "." + method + " (" + n + ")");
            return n;
        } catch (e) { return 0; }
    }

    var LMS = findClass(["com.android.server.location.LocationManagerService", "com.android.server.LocationManagerService"]);
    var _g = 0;
    hookAll(LMS, "getLastLocation", function (ov) {
        return function () {
            var r = ov.apply(this, arguments);
            try { var c = coords(); if (c) { if (_g++ < 5) log("getLastLocation -> FAKE " + c.lat + "," + c.lng); return makeFake(r, c); } } catch (e) {}
            return r;
        };
    }, "LMS");

    // getCurrentLocation: bloqueia enquanto spoofando (app cai pro getLastLocation fake)
    var _cc = 0;
    hookAll(LMS, "getCurrentLocation", function (ov) {
        return function () {
            try { var c = coords(); if (c) { if (_cc++ < 3) log("getCurrentLocation BLOQUEADO"); return null; } } catch (e) {}
            return ov.apply(this, arguments);
        };
    }, "LMS");

    // GNSS bruto: bloqueia p/ nao vazar localizacao real
    var gnssMethods = ["registerGnssStatusCallback", "registerGnssNmeaCallback", "addGnssMeasurementsListener",
                       "addGnssNavigationMessageListener", "addGnssAntennaInfoListener", "addGnssBatchingCallback"];
    var GMS = findClass(["com.android.server.location.gnss.GnssManagerService"]);
    gnssMethods.forEach(function (mn) {
        hookAll(LMS, mn, function (ov) { return function () { try { if (coords()) return null; } catch (e) {} return ov.apply(this, arguments); }; }, "LMS");
        hookAll(GMS, mn, function (ov) { return function () { try { if (coords()) return null; } catch (e) {} return ov.apply(this, arguments); }; }, "GMS");
    });

    // updates ao vivo (LocationProviderManager.onReportLocation): reescreve todas as Location
    var LPM = findClass(["com.android.server.location.provider.LocationProviderManager"]);
    var _r = 0;
    if (LPM) {
        try {
            var onR = LPM.onReportLocation.overload("android.location.LocationResult");
            onR.implementation = function (lr) {
                try {
                    var c = coords();
                    if (c && lr) {
                        var locs = lr.getLocations();
                        for (var i = 0; i < locs.size(); i++) makeFake(locs.get(i), c);
                        if (_r++ < 5) log("onReportLocation -> FAKE " + c.lat + "," + c.lng);
                    }
                } catch (e) {}
                return onR.call(this, lr);
            };
            log("hooked LPM.onReportLocation");
        } catch (e) { log("onReportLocation err: " + e); }
    }

    var c0 = coords();
    log("INSTALADO. coords=" + (c0 ? c0.lat + "," + c0.lng : "null") + "  file=" + COORD_FILE);
});
