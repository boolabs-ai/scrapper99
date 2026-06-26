// hook_location.js - Hook de localização para Frida
// Uso: frida -U -f com.app.alvo -l hook_location.js --no-pause

Java.perform(function() {
    //console.log("[+] Iniciando hook de localização para Curitiba");
    
    // 1. Hook para LocationManager
    var LocationManager = Java.use("android.location.LocationManager");
    
    // Hook getLastKnownLocation
    LocationManager.getLastKnownLocation.overload('java.lang.String').implementation = function(provider) {
        //console.log("[+] LocationManager.getLastKnownLocation chamado. Provider: " + provider);
        var location = this.getLastKnownLocation(provider);
        if (location) {
            location.setLatitude(-23.5629); 
            location.setLongitude(-46.6544); 
            location.setAccuracy(20.0);      // Precisão de 20 metros
            ////console.log("[+] Localização modificada para São Paulo (via getLastKnownLocation)");
        }
        
        return location;
    };
    
    // 2. Hook para Location class diretamente
    var Location = Java.use("android.location.Location");
    
    // Hook do construtor
    Location.$init.overload('java.lang.String').implementation = function(provider) {
        //console.log("[+] Location() constructor chamado");
        var result = this.$init(provider);
        this.setLatitude(-23.5629);
        this.setLongitude(-46.6544);
        this.setAccuracy(20.0);
        this.setTime(Date.now());
        return result;
    };
    
    // Hook dos métodos getters
    Location.getLatitude.implementation = function() {
        var original = this.getLatitude();
        //console.log("[+] Location.getLatitude() chamado. Original: " + original + ", Sobrescrito: -23.5505");
        return -23.5629;
    };
    
    Location.getLongitude.implementation = function() {
        var original = this.getLongitude();
        //console.log("[+] Location.getLongitude() chamado. Original: " + original + ", Sobrescrito: -46.6333");
        return -46.6544;
    };
    
    // 3. Hook para FusedLocationProviderClient (Google Play Services)
    try {
        var FusedLocationProviderClient = Java.use("com.google.android.gms.location.FusedLocationProviderClient");
        
        FusedLocationProviderClient.getLastLocation.implementation = function() {
            //console.log("[+] FusedLocationProviderClient.getLastLocation() chamado");
            // Retorna uma Promise/Task que podemos modificar
            return this.getLastLocation();
        };
        
        //console.log("[+] Hook do FusedLocationProviderClient aplicado");
    } catch (e) {
        //console.log("[-] FusedLocationProviderClient não encontrado: " + e);
    }
    
    // 4. Hook para métodos de mock location (para apps que verificam)
    LocationManager.isProviderEnabled.overload('java.lang.String').implementation = function(provider) {
        //console.log("[+] LocationManager.isProviderEnabled chamado para: " + provider);
        
        if (provider === "network" || provider === "gps" || provider === "passive") {
            //console.log("[+] Provider " + provider + " retornando true (habilitado)");
            return true;
        }
        
        return this.isProviderEnabled(provider);
    };
    
    // 5. Hook para verificação de mock location (Android 6.0+)
    Location.isFromMockProvider.implementation = function() {
        //console.log("[+] Location.isFromMockProvider() chamado. Retornando false para evitar detecção.");
        return false;
    };
    
    //console.log("[+] Todos os hooks de localização aplicados com sucesso!");
    //console.log("[+] Localização fixada: São Paulo (-23.5505, -46.6333)");
});

// Função para mudar dinamicamente a localização
function changeLocation(lat, lng) {
    Java.perform(function() {
        global_latitude = lat;
        global_longitude = lng;
        //console.log("[+] Localização alterada para: " + lat + ", " + lng);
    });
}

// Comandos úteis no console do Frida:
// changeLocation(-23.5505, -46.6333);  // Centro de São Paulo
// changeLocation(-23.5629, -46.6544);  // Av. Paulista
// changeLocation(-23.5882, -46.6324);  // Ibirapuera