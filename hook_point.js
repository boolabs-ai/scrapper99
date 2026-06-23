// hook_point.js — extrai pointId/lat/lng/cityId dos requests HTTP do app ao nivel Java.
//
// Hooks okhttp3.Request e didihttp.Request antes da criptografia.
// O app envia esses campos no body de todos os requests para didi-food.com,
// incluindo feed/indexV3, shop/index, etc.
//
// Grava em: /data/data/com.taxis99/files/cur_point.json
// Formato:  { "pointId": "...", "lat": "...", "lng": "...", "cityId": "...", "poiId": "..." }
//
// Uso: frida -U -q -p <PID> -l hook_point.js
Java.perform(function () {
    var PKG = 'com.taxis99';
    var OUT = '/data/data/' + PKG + '/files/cur_point.json';
    var FOS = Java.use('java.io.FileOutputStream');
    var JStr = Java.use('java.lang.String');

    function save(obj) {
        try {
            var s = JSON.stringify(obj);
            var bytes = JStr.$new(s).getBytes('UTF-8');
            var f = FOS.$new(OUT, false); // sobrescreve — queremos sempre o mais recente
            f.write(bytes);
            f.close();
            console.log('[point] capturado -> ' + s);
        } catch (e) {}
    }

    // extrai campos de interesse de body form-encoded ou JSON
    function parseBody(body) {
        if (!body || body.length === 0) return null;
        var result = {};

        // tenta JSON
        try {
            var o = JSON.parse(body);
            ['pointId','lat','lng','cityId','poiId','poiLat','poiLng'].forEach(function(k) {
                if (o[k] !== undefined && o[k] !== null && o[k] !== '') result[k] = String(o[k]);
            });
        } catch (_) {}

        // tenta form-encoded (page=0&lat=...&lng=...&pointId=...)
        ['pointId','lat','lng','cityId','poiId','poiLat','poiLng'].forEach(function(k) {
            if (result[k]) return;
            var re = new RegExp('(?:^|&)' + k + '=([^&]+)');
            var m = body.match(re);
            if (m) {
                try { result[k] = decodeURIComponent(m[1].replace(/\+/g, ' ')); }
                catch (_) { result[k] = m[1]; }
            }
        });

        // so salva se tem pelo menos lat+lng ou pointId
        var hasCoords = result.lat && result.lng &&
                        result.lat !== '0' && result.lng !== '0';
        var hasPoint  = result.pointId && result.pointId.length > 1;
        return (hasCoords || hasPoint) ? result : null;
    }

    var last = '';

    function hookClass(cls) {
        Java.enumerateClassLoaders({
            onMatch: function (loader) {
                var f;
                try { f = Java.ClassFactory.get(loader); } catch (e) { return; }
                var Req;
                try { Req = f.use(cls); } catch (e) { return; }

                var Buffer;
                try { Buffer = f.use('okio.Buffer'); } catch (e) { return; }

                try {
                    Req.headers.overload().implementation = function () {
                        var hdrs = Req.headers.overload().call(this);
                        try {
                            var url = String(this.url().toString());
                            // so intercepta requests para a API do DiDi Food
                            if (url.indexOf('didi-food.com') < 0 && url.indexOf('taxis99') < 0) return hdrs;

                            var rb = this.body();
                            if (!rb) return hdrs;

                            var buf = Buffer.$new();
                            rb.writeTo(buf);
                            var bodyStr = String(buf.readUtf8());

                            var parsed = parseBody(bodyStr);
                            if (!parsed) return hdrs;

                            var key = (parsed.lat || '') + '|' + (parsed.lng || '') + '|' + (parsed.pointId || '');
                            if (key === last) return hdrs;
                            last = key;
                            save(parsed);
                        } catch (_) {}
                        return hdrs;
                    };
                    console.log('[point] ' + cls + ' hookado (loader: ' + loader + ')');
                } catch (e) {}
            },
            onComplete: function () {}
        });
    }

    hookClass('okhttp3.Request');
    hookClass('didihttp.Request');
});
