// probe_loc.js — SPIKE: testa se o XposedFakeLocation injeta coords no app alvo.
// Hooka varios pontos de leitura de localizacao. Se o mock propagou, lat/lng
// retornados serao os do datastore (ex: -23.55/-46.63), nao a localizacao real.
Java.perform(function () {
    var seen = {};
    function log(tag, lat, lng, extra) {
        var k = tag + lat.toFixed(5) + lng.toFixed(5);
        if (seen[k]) return; seen[k] = 1;
        console.log('[probe] ' + tag + ' -> ' + lat + ', ' + lng + (extra ? '  ' + extra : ''));
    }

    try {
        var Location = Java.use('android.location.Location');
        Location.getLatitude.implementation = function () {
            var v = this.getLatitude.call(this);
            try { log('Location.getLatitude', v, this.getLongitude.call(this), 'provider=' + this.getProvider()); } catch (e) {}
            return v;
        };
    } catch (e) { console.log('[probe] Location hook err ' + e); }

    try {
        var LM = Java.use('android.location.LocationManager');
        LM.getLastKnownLocation.overload('java.lang.String').implementation = function (p) {
            var loc = this.getLastKnownLocation.call(this, p);
            try { if (loc) log('getLastKnownLocation(' + p + ')', loc.getLatitude(), loc.getLongitude()); } catch (e) {}
            return loc;
        };
    } catch (e) { console.log('[probe] LM hook err ' + e); }

    // GMS FusedLocationProviderClient.getLastLocation retorna Task<Location>;
    // o resultado e' lido via getLatitude da Location -> ja coberto acima.
    console.log('[probe] hooks instalados (Location + LocationManager) — aguardando leitura...');
});
