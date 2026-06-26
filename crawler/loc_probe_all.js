// loc_probe_all.js — loga TODAS as formas do 99 ler localizacao, p/ achar o ponto de hook.
Java.perform(function () {
    function log(m){ console.log("[loc] " + m); }
    function stack(){ try { return Java.use("android.util.Log").getStackTraceString(Java.use("java.lang.Exception").$new()).split("\n").slice(1,5).join(" | "); } catch(e){ return ""; } }
    log("start");
    var LM = Java.use("android.location.LocationManager");

    LM.getLastKnownLocation.overloads.forEach(function(ov){
        ov.implementation = function(){ log("getLastKnownLocation args="+arguments.length); return ov.apply(this, arguments); };
    });
    log("hooked getLastKnownLocation ("+LM.getLastKnownLocation.overloads.length+")");

    LM.requestLocationUpdates.overloads.forEach(function(ov, i){
        ov.implementation = function(){
            log("requestLocationUpdates ov#"+i+" argc="+arguments.length+" :: "+stack());
            return ov.apply(this, arguments);
        };
    });
    log("hooked requestLocationUpdates ("+LM.requestLocationUpdates.overloads.length+")");

    try { LM.requestSingleUpdate.overloads.forEach(function(ov){ ov.implementation=function(){ log("requestSingleUpdate argc="+arguments.length); return ov.apply(this,arguments);};}); log("hooked requestSingleUpdate"); } catch(e){}
    try { LM.addNmeaListener.overloads.forEach(function(ov){ ov.implementation=function(){ log("addNmeaListener argc="+arguments.length); return ov.apply(this,arguments);};}); log("hooked addNmeaListener"); } catch(e){}
    try { LM.registerGnssStatusCallback.overloads.forEach(function(ov){ ov.implementation=function(){ log("registerGnssStatusCallback"); return ov.apply(this,arguments);};}); log("hooked registerGnssStatusCallback"); } catch(e){}
    try { LM.getCurrentLocation.overloads.forEach(function(ov){ ov.implementation=function(){ log("getCurrentLocation"); return ov.apply(this,arguments);};}); log("hooked getCurrentLocation"); } catch(e){}

    // GMS fused
    try {
        var FLPC = Java.use("com.google.android.gms.location.FusedLocationProviderClient");
        FLPC.getLastLocation.overloads.forEach(function(ov){ ov.implementation=function(){ log("FLPC.getLastLocation :: "+stack()); return ov.apply(this,arguments);};});
        FLPC.requestLocationUpdates.overloads.forEach(function(ov){ ov.implementation=function(){ log("FLPC.requestLocationUpdates argc="+arguments.length); return ov.apply(this,arguments);};});
        log("hooked FLPC");
    } catch(e){ log("FLPC: "+e); }

    log("instalado; aguardando...");
});
