Java.perform(function(){
  function log(m){ console.log("[ss] "+m); }
  var hits=[];
  Java.enumerateLoadedClassesSync().forEach(function(c){
    if (/com\.android\.server\.location/.test(c) && /(ProviderManager|LocationManagerService|Gnss|injector|LocationProvider)/.test(c)) hits.push(c);
  });
  log("classes de localizacao ("+hits.length+"):");
  hits.slice(0,40).forEach(function(c){ log("  "+c); });
});
