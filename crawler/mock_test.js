// mock_test.js — versão de TESTE do mock-lockation.js, com LOGS, p/ ver se o 99
// realmente chama as APIs de localização que dá pra hookar via Frida.
// Retorna SP (Av. Paulista) e loga cada chamada.
var LAT = -23.5629, LNG = -46.6544;

Java.perform(function () {
    function log(m) { console.log("[mock] " + m); }
    log("instalando hooks...");

    var LM = Java.use("android.location.LocationManager");
    LM.getLastKnownLocation.overload('java.lang.String').implementation = function (p) {
        var loc = this.getLastKnownLocation(p);
        log("getLastKnownLocation(" + p + ") -> " + (loc ? loc.getLatitude() + "," + loc.getLongitude() : "null") + "  [forcando SP]");
        if (loc) { loc.setLatitude(LAT); loc.setLongitude(LNG); loc.setAccuracy(20.0); }
        return loc;
    };
    try {
        LM.requestLocationUpdates.overload('java.lang.String','long','float','android.location.LocationListener').implementation = function (p,a,b,l) {
            log("requestLocationUpdates(" + p + ")");
            return this.requestLocationUpdates(p,a,b,l);
        };
    } catch (e) { log("requestLocationUpdates overload nao encontrado"); }

    var Location = Java.use("android.location.Location");
    var seen = {};
    Location.getLatitude.implementation = function () {
        var v = this.getLatitude();
        if (!seen['la']) { seen['la']=1; log("Location.getLatitude() original=" + v + " provider=" + this.getProvider() + " -> SP"); }
        return LAT;
    };
    Location.getLongitude.implementation = function () { return LNG; };
    Location.isFromMockProvider.implementation = function () { return false; };

    // GMS FusedLocationProviderClient
    try {
        var FLPC = Java.use("com.google.android.gms.location.FusedLocationProviderClient");
        log("FusedLocationProviderClient encontrado (classe existe no processo)");
    } catch (e) { log("FusedLocationProviderClient NAO encontrado neste processo"); }

    log("hooks instalados. aguardando o app ler localizacao...");
});
