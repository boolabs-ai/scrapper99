Java.perform(function(){
  var AT = Java.use('android.app.ActivityThread');
  var ctx = AT.currentApplication().getApplicationContext();
  var lm = ctx.getSystemService("location");
  var LM = Java.use('android.location.LocationManager');
  lm = Java.cast(lm, LM);
  var n=0;
  var t=setInterval(function(){ Java.perform(function(){
    try { var l = lm.getLastKnownLocation("gps");
      console.log("[test] getLastKnownLocation(gps) -> " + (l? l.getLatitude().toFixed(4)+","+l.getLongitude().toFixed(4) : "null"));
    } catch(e){ console.log("[test] err "+e); }
    if(++n>=5) clearInterval(t);
  });}, 1500);
});
