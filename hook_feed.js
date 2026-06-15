/**************************************************************************************
 * hook_feed.js — extrai o feed de restaurantes do 99/DiDi Food (com.taxis99) da HEAP.
 *
 * Como funciona:
 *   O feed é nativo (com.didi.soda) num classloader isolado, e a resposta da API
 *   (Cronet/QUIC) escapa de toda captura de rede. Mas o objeto JÁ PARSEADO
 *   (HomeFeedEntity) vive na memória. Este script:
 *     1. Enumera TODOS os classloaders (a DiDi usa plugin framework).
 *     2. Para cada um que carrega as entidades do feed, usa Java.choose pra achar
 *        as instâncias vivas na heap.
 *     3. Serializa cada uma com Gson e ACRESCENTA (append) numa JSONL:
 *        /data/data/com.taxis99/files/heap_all.jsonl  (uma entidade por linha).
 *
 *   Roda na injeção (grab() na carga). O scrape.ps1 ataca este script repetidas vezes
 *   (entre scrolls) — cada ataque acrescenta as páginas atualmente na memória.
 *
 * Uso: frida -H 127.0.0.1:2222 -q -p <PID_DO_APP> -l hook_feed.js
 **************************************************************************************/
Java.perform(function () {
    var PKG = 'com.taxis99';
    var OUT = '/data/data/' + PKG + '/files/heap_all.jsonl';
    var FOS = Java.use('java.io.FileOutputStream');
    var JString = Java.use('java.lang.String');

    // Entidades do feed (cada uma = uma página: {hasMore, compList, filterList, type})
    var ENT = [
        'com.didi.soda.customer.foundation.rpc.entity.topgun.HomeFeedEntity',
        'com.didi.soda.customer.foundation.rpc.entity.topgun.HomeModuleEntity',
        'com.didi.soda.customer.foundation.rpc.entity.topgun.FeedEntity',
        'com.didi.soda.customer.foundation.rpc.entity.ModuleEntity'
    ];

    function append(jsonl) {
        try { var f = FOS.$new(OUT, true); f.write(JString.$new(jsonl + '\n').getBytes('UTF-8')); f.close(); } catch (e) {}
    }

    var seen = {}; // evita re-choose da mesma classe em loaders diferentes nesta sessão

    Java.enumerateClassLoaders({
        onMatch: function (loader) {
            var f;
            try { f = Java.ClassFactory.get(loader); } catch (e) { return; }
            var gson = null;
            try { gson = f.use('com.google.gson.Gson').$new(); } catch (e) {}
            if (!gson) return;
            ENT.forEach(function (cn) {
                if (seen[cn]) return;
                try { f.use(cn); } catch (e) { return; } // este loader tem a classe?
                try {
                    f.choose(cn, {
                        onMatch: function (inst) {
                            try {
                                var j = gson.toJson(inst);
                                if (j && j.length > 100 && j.indexOf('shopId') >= 0) append(j);
                            } catch (e) {}
                        },
                        onComplete: function () { seen[cn] = true; }
                    });
                } catch (e) {}
            });
        },
        onComplete: function () {}
    });
});
