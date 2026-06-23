<#
  scrape.ps1 — captura o feed de restaurantes do 99 Food.

  Faz, automaticamente:
    1. SELinux permissive (setenforce 0)  -- necessario pro frida injetar.
    2. Sobe o fserver (frida-server 17.6.1) na porta 2222 + adb forward (se nao estiver no ar).
    3. Acha o PID do app (precisa estar ABERTO na aba Comida).
    4. LOOP: autoscroll (adb input swipe) + injeta hook_feed.js (heap scan) -> acumula
       as paginas do feed em heap_all.jsonl.
    5. Puxa heap_all.jsonl e roda consolidate.py -> restaurantes.json (+ _full.json).

  Pre-req: ter rodado .\setup.ps1 uma vez, e o app 99 ABERTO na lista de restaurantes (Comida).

  Uso:
    .\scrape.ps1                       # 8 ciclos, 6 swipes/ciclo
    .\scrape.ps1 -Cycles 15 -SwipesPerCycle 8   # mais agressivo (mais lojas)
#>
param(
    [int]$Cycles = 8,
    [int]$SwipesPerCycle = 6,
    [int]$ScanSeconds = 10,
    [string]$DeviceId = '99_food_app',
    [string]$PointId  = '',
    [string]$Lat      = '',
    [string]$Lng      = '',
    [string]$CityId   = '',
    [string]$PoiId    = ''
)
$ErrorActionPreference = 'Continue'
$adb  = 'adb'
$PKG  = 'com.taxis99'
$HERE = $PSScriptRoot
$HEAP = "/data/data/$PKG/files/heap_all.jsonl"
function Step($m) { Write-Host "[*] $m" -ForegroundColor Cyan }

# 1) device + permissive
if ((& $adb get-state 2>$null) -ne 'device') { Write-Error "Device nao conectado (adb)."; exit 1 }
& $adb shell su -c "setenforce 0" 2>$null
Step "SELinux = $(& $adb shell getenforce 2>$null)"

# 2) fserver na 2222
if (-not (& $adb shell su -c "pidof fserver" 2>$null)) {
    Step "Subindo fserver (frida-server 17.6.1)..."
    & $adb shell su -c "nohup /data/local/tmp/fserver -l 0.0.0.0:2222 >/dev/null 2>&1 &" 2>$null
    Start-Sleep -Seconds 3
}
& $adb forward tcp:2222 tcp:2222 | Out-Null
Step "frida CLI = $(& frida --version 2>$null)  (esperado 17.6.1)"

# 3) dimensoes da tela
$w = 1080; $h = 2400
$size = (& $adb shell wm size 2>$null)
if ($size -match '(\d+)x(\d+)') { $w = [int]$Matches[1]; $h = [int]$Matches[2] }
$x = [int]($w * 0.5); $y1 = [int]($h * 0.72); $y2 = [int]($h * 0.28)

# 4) abre o app se nao estiver rodando
$apid = "$(& $adb shell pidof $PKG 2>$null)".Trim()
if (-not $apid) {
    Step "App nao esta aberto -> abrindo o 99..."
    & $adb shell "monkey -p $PKG -c android.intent.category.LAUNCHER 1" 2>$null | Out-Null
    for ($t = 0; $t -lt 20; $t++) { Start-Sleep -Seconds 2; $apid = "$(& $adb shell pidof $PKG 2>$null)".Trim(); if ($apid) { break } }
    Start-Sleep -Seconds 8   # deixa passar do splash / carregar
    $apid = "$(& $adb shell pidof $PKG 2>$null)".Trim()
}
if (-not $apid) { Write-Error "Nao consegui abrir o $PKG. Verifique se esta instalado/logado."; exit 1 }
Step "App $PKG pid=$apid"

# 5) limpa acumulador
& $adb shell su -c "rm -f $HEAP" 2>$null

# 6) LOOP autoscroll + heap-scan
Step "Loop: $Cycles ciclos x $SwipesPerCycle swipes (role a lista do Food)..."
for ($c = 1; $c -le $Cycles; $c++) {
    for ($s = 1; $s -le $SwipesPerCycle; $s++) {
        & $adb shell input swipe $x $y1 $x $y2 450 2>$null
        Start-Sleep -Milliseconds 1000
    }
    # injeta o heap-scan (roda na carga, acrescenta as paginas vivas) e mata apos ScanSeconds
    $argline = '-H 127.0.0.1:2222 -q -p {0} -l "{1}\hook_feed.js"' -f $apid, $HERE
    $proc = Start-Process -FilePath "frida" -ArgumentList $argline -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds $ScanSeconds
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $n = (& $adb shell su -c "cat $HEAP 2>/dev/null | wc -l" 2>$null)
    $n = if ($n) { "$n".Trim() } else { '?' }
    Write-Host ("    ciclo {0}/{1} -> {2} entidades acumuladas" -f $c, $Cycles, $n)
    # se o app morreu, para
    if (-not "$(& $adb shell pidof $PKG 2>$null)".Trim()) { Write-Host "[!] app fechou; parando o loop."; break }
}

# 7) puxa o acumulador
& $adb shell su -c "cp $HEAP /sdcard/heap_all.jsonl; chmod 666 /sdcard/heap_all.jsonl" 2>$null
& $adb pull /sdcard/heap_all.jsonl "$HERE\heap_all.jsonl" 2>$null | Out-Null

# 8) le coords do ponto de entrega (AddressStorage binary) + cityId (routing_location_cache)
if ((-not $Lat) -or (-not $Lng)) {
    # AddressStorage guarda o POI de entrega como IEEE 754 doubles em binario base64
    $addrXml = (& $adb shell su -c "cat '/data/data/$PKG/shared_prefs/com.didi.soda.address.manager.AddressStorage.xml'" 2>$null) -join ""
    if ($addrXml -match '<string name="Storage.Key">([^<]+)</string>') {
        $b64 = $Matches[1].Trim() -replace '\s','' -replace '&#10;',''
        try {
            $bytes = [Convert]::FromBase64String($b64)
            # varre procurando par (lat, lng) valido para o Brasil
            for ($i = 0; $i -le $bytes.Length - 16; $i++) {
                $dLat = [BitConverter]::ToDouble($bytes, $i)
                $dLng = [BitConverter]::ToDouble($bytes, $i + 8)
                if ($dLat -lt -3 -and $dLat -gt -35 -and $dLng -lt -30 -and $dLng -gt -75) {
                    $Lat = "$dLat"; $Lng = "$dLng"; break
                }
            }
        } catch { }
    }
}
if (-not $CityId) {
    $routeXml = (& $adb shell su -c "cat '/data/data/$PKG/shared_prefs/routing_location_cache.xml'" 2>$null) -join ""
    if ($routeXml -match 'lCity[^>]*>([^<]+)<') { $CityId = $Matches[1].Trim() }
}
if (-not $PointId -and $Lat -and $Lng) { $PointId = "${Lat}_${Lng}" }
Step "Coords: lat=$Lat  lng=$Lng  cityId=$CityId  point_id=$PointId"

# 9) consolida
Write-Host ""
python "$HERE\consolidate.py" "$HERE" "$Lat" "$Lng" "$CityId"
Write-Host ""
Step "PRONTO -> $HERE\restaurantes.json  e  restaurantes_full.json"

# 10) envia pro Tinybird
if ($Lat -and $Lng) {
    Step "Enviando pro Tinybird..."
    & "$HERE\tinybird_send.ps1" -HeapPath "$HERE\heap_all.jsonl" -DeviceId $DeviceId -PointId $PointId -Lat $Lat -Lng $Lng -CityId $CityId -PoiId $PoiId
    Step "tinybird_send concluido (exit=$LASTEXITCODE)"
} else {
    Write-Host "[!] Coords ausentes - tinybird_send pulado." -ForegroundColor Yellow
}
