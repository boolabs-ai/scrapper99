Java.perform(function(){
  function log(m){ console.log("[ss] "+m); }
  var C = Java.use("com.android.server.location.provider.LocationProviderManager");
  var names = {};
  C.class.getDeclaredMethods().forEach(function(m){
    var n=m.getName();
    if (/[Ll]astLocation|[Rr]eportLocation|onReport|injectLastLocation/.test(n)) {
      var params = m.getParameterTypes().map(function(p){return p.getName();}).join(",");
      log(n+"("+params+") : "+m.getReturnType().getName());
    }
  });
});
