Java.perform(function(){
  function log(m){ console.log("[ss] "+m); }
  ["com.android.server.location.provider.LocationProviderManager"].forEach(function(cn){
    try {
      var C = Java.use(cn);
      var ms = C.class.getDeclaredMethods();
      log("=== "+cn+" ("+ms.length+" metodos) ===");
      ms.forEach(function(m){
        var s=m.toString();
        if (/[Ll]ocation|[Rr]eport|[Dd]eliver|getLast|inject/.test(s)) log("  "+s.replace(/.*location\.provider\./,''));
      });
    } catch(e){ log(cn+" erro: "+e); }
  });
});
