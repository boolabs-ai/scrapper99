// mock_test2.js — descobre o caminho de localizacao do 99 (GMS fused / SDK propria).
// Loga e tenta reescrever. Hooka FusedLocationProviderClient + LocationResult +
// LocationCallback, e varre classloaders por classes de localizacao da DiDi.
var LAT = -23.5629, LNG = -46.6544;

Java.perform(function () {
    function log(m){ console.log("[mt2] " + m); }
    log("start");

    // --- GMS FusedLocationProviderClient ---
    try {
        var FLPC = Java.use("com.google.android.gms.location.FusedLocationProviderClient");
        FLPC.getLastLocation.overloads.forEach(function(ov){
            ov.implementation = function(){ log("FLPC.getLastLocation() chamado (args="+arguments.length+")"); return ov.apply(this, arguments); };
        });
        log("hooked FLPC.getLastLocation ("+FLPC.getLastLocation.overloads.length+" ov)");
        if (FLPC.getCurrentLocation) {
            FLPC.getCurrentLocation.overloads.forEach(function(ov){
                ov.implementation = function(){ log("FLPC.getCurrentLocation() chamado"); return ov.apply(this, arguments); };
            });
            log("hooked FLPC.getCurrentLocation");
        }
        FLPC.requestLocationUpdates.overloads.forEach(function(ov){
            ov.implementation = function(){ log("FLPC.requestLocationUpdates() chamado (args="+arguments.length+")"); return ov.apply(this, arguments); };
        });
        log("hooked FLPC.requestLocationUpdates");
    } catch (e) { log("FLPC erro: " + e); }

    // --- LocationResult / LocationCallback (onde chega o fix do fused) ---
    try {
        var LR = Java.use("com.google.android.gms.location.LocationResult");
        LR.getLastLocation.implementation = function(){
            var loc = this.getLastLocation();
            log("LocationResult.getLastLocation -> " + (loc? loc.getLatitude()+","+loc.getLongitude():"null") + " [reescrevendo SP]");
            if (loc){ loc.setLatitude(LAT); loc.setLongitude(LNG); }
            return loc;
        };
        log("hooked LocationResult.getLastLocation");
    } catch (e) { log("LocationResult erro: " + e); }

    // --- Task.getResult (resultado do getLastLocation costuma ser Task<Location>) ---
    try {
        var Task = Java.use("com.google.android.gms.tasks.Task");
        Task.getResult.overload().implementation = function(){
            var r = this.getResult();
            try { if (r && r.getClass().getName().indexOf("Location")>=0) log("Task.getResult -> Location " + r.getLatitude()+","+r.getLongitude()); } catch(e){}
            return r;
        };
        log("hooked Task.getResult");
    } catch (e) { log("Task erro: " + e); }

    // --- varre classes de localizacao da DiDi (didi/amap) ---
    try {
        var loaders = Java.enumerateClassLoadersSync();
        var found = {};
        loaders.forEach(function(ld){
            try {
                var f = Java.ClassFactory.get(ld);
            } catch(e){}
        });
        log("classloaders: " + loaders.length);
    } catch (e) {}

    log("hooks instalados; aguardando leitura de localizacao do 99...");
});
