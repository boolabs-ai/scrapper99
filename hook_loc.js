// hook_loc.js — captura as coords do ponto atual via SSL_write.
//
// O app envia lat/lng/cityId no body/query de TODOS os requests okhttp/didihttp.
// Hookando SSL_write da libssl.so (stack TLS do sistema) lemos esses valores
// antes de serem criptografados. Requests Cronet/QUIC usam BoringSSL proprio e
// NAO passam por aqui — mas o app sempre faz requests nao-Cronet (analytics,
// enderecos, campanhas, etc.) que contem lat/lng, entao as coords sao capturadas.
//
// Grava em: /data/data/com.taxis99/files/cur_loc.txt
// Formato:  lat|lng|cityId  (ex: -30.0277|-51.2287|4501)
//
// Uso: frida -U -q -p <PID> -l hook_loc.js
(function () {
    var DIR = '/data/data/com.taxis99/files/';
    var OUT = DIR + 'cur_loc.txt';

    var m = Process.findModuleByName('libssl.so');
    if (!m) { console.log('[loc] libssl.so nao encontrada'); return; }
    var w = m.findExportByName('SSL_write');
    if (!w) { console.log('[loc] SSL_write nao encontrado em libssl.so'); return; }

    var last = '';

    Interceptor.attach(w, {
        onEnter: function (args) {
            try {
                var n = args[2].toInt32();
                if (n <= 0 || n > 300000) return;

                // converte o buffer para ASCII imprimivel
                var u8 = new Uint8Array(args[1].readByteArray(n));
                var s = '';
                for (var i = 0; i < u8.length; i++) {
                    var c = u8[i];
                    s += (c >= 32 && c < 127) ? String.fromCharCode(c) : ' ';
                }

                // tenta extrair lat/lng de JSON ou query string
                var mm = s.match(/"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lng"\s*:\s*(-?\d+\.\d+)/)
                      || s.match(/[&?]lat=(-?\d+\.\d+)&lng=(-?\d+\.\d+)/)
                      || s.match(/"latitude"\s*:\s*(-?\d+\.\d+)[\s\S]{0,40}?"longitude"\s*:\s*(-?\d+\.\d+)/);
                if (!mm) return;

                // tenta extrair cityId
                var cm = s.match(/location_cityid"?\s*[:=]\s*"?(\d{4,})/)
                      || s.match(/trip_cityid=(\d{4,})/)
                      || s.match(/"cityId"\s*:\s*"?(\d{4,})/);

                var rec = mm[1] + '|' + mm[2] + '|' + (cm ? cm[1] : '');
                if (rec === last) return;
                last = rec;

                try {
                    var f = new File(OUT, 'w');
                    f.write(rec);
                    f.close();
                } catch (e) {}

                console.log('[loc] coords capturadas -> ' + rec);
            } catch (e) {}
        }
    });

    console.log('[loc] SSL_write hookado em ' + m.name + ' — aguardando requests do app...');
})();
