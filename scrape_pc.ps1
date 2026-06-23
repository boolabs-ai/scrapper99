<#
  scrape_pc.ps1 - scraper do feed do 99 Food (Android 15, com.taxis99).

  Fluxo:
    1. SELinux permissive + fserver2.
    2. Le coords do ponto de entrega em com.didi.map.xml (key_params.lat/lng/cityId).
       Esses valores sao gravados pelo app ao receber a config do servidor DiDi via TCP.
    3. Abre o app na aba Comida.
    4. Injeta hook_feed.js (heap-scan + setInterval) + scroll continuo
       -> acumula paginas do feed em heap_all.jsonl.
    5. Puxa heap_all.jsonl do device.
    6. consolidate.py -> restaurantes.json / restaurantes_full.json.
    7. tinybird_send.ps1 -> posta no Tinybird -> Grafana.

  Uso:
    .\scrape_pc.ps1
    .\scrape_pc.ps1 -Cycles 12 -SwipesPerCycle 8
    .\scrape_pc.ps1 -Lat -22.9312 -Lng -43.2453 -CityId 55000161
#>
param(
    [int]$Cycles          = 8,
    [int]$SwipesPerCycle  = 12,
    [string]$DeviceId     = '99_food_app',
    [string]$PointId      = '',
    [string]$Lat          = '',
    [string]$Lng          = '',
    [string]$CityId       = '',
    [string]$PoiId        = ''
)

$ErrorActionPreference = 'Continue'
$adb      = 'adb'
$PKG      = 'com.taxis99'
$HERE     = $PSScriptRoot
$HEAP     = "/data/data/$PKG/files/heap_all.jsonl"
$hookFeed = Join-Path $HERE 'hook_feed.js'

function Step($m) { Write-Host "[*] $m" -ForegroundColor Cyan }

# 1. device + SELinux + fserver2
if ((& $adb get-state 2>$null) -ne 'device') {
    Write-Error "Device nao conectado (adb)."
    exit 1
}
& $adb shell su -c "setenforce 0" 2>$null
Step "SELinux = $(& $adb shell getenforce 2>$null)"

$fsPid = (& $adb shell su -c "pidof fserver2" 2>$null)
if (-not $fsPid) {
    Step "Subindo fserver2..."
    & $adb shell su -c "nohup /data/local/tmp/fserver2 >/dev/null 2>&1 &" 2>$null
    Start-Sleep 3
}
Step "frida CLI = $(& frida --version 2>$null)"

# 2. abre o app
Step "Abrindo o 99..."
& $adb shell "monkey -p $PKG -c android.intent.category.LAUNCHER 1" 2>$null | Out-Null

$apid = ''
for ($t = 0; $t -lt 20; $t++) {
    Start-Sleep 1
    $apid = (& $adb shell pidof $PKG 2>$null)
    if ($apid) { $apid = $apid.Trim(); break }
}
if (-not $apid) { Write-Error "Nao consegui abrir o $PKG."; exit 1 }

Step "App aberto (pid=$apid). Aguardando 12s para carregar e atualizar coords..."
Start-Sleep 12

$apid = (& $adb shell pidof $PKG 2>$null)
if (-not $apid) { Write-Error "App fechou durante a espera."; exit 1 }
$apid = $apid.Trim()

# 3. le coords apos o app ter contatado o servidor (key_params atualizado por TCP)
if ((-not $Lat) -or (-not $Lng)) {
    $mapXml = (& $adb shell su -c "cat '/data/data/$PKG/shared_prefs/sdk_sharedpreference.xml'" 2>$null) -join ""
    if ($mapXml -match 'key_params[^>]*>([^<]+)<') {
        $kpRaw = $Matches[1] -replace '&quot;','"' -replace '&#10;',''
        $kp = $kpRaw | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($kp) {
            if (-not $Lat    -and $kp.lat)    { $Lat    = "$($kp.lat)" }
            if (-not $Lng    -and $kp.lng)    { $Lng    = "$($kp.lng)" }
            if (-not $CityId -and $kp.cityId) { $CityId = "$($kp.cityId)" }
        }
    }
}
if (-not $Lat -or -not $Lng) {
    Write-Host "[!] Coords nao encontradas em com.didi.map.xml. Passe -Lat e -Lng." -ForegroundColor Yellow
    exit 1
}
if (-not $PointId) { $PointId = "${Lat}_${Lng}" }
Step "Coords (key_params/TCP) -> lat=$Lat  lng=$Lng  cityId=$CityId  point_id=$PointId"

$w = 1080; $h = 2400
$sz = (& $adb shell wm size 2>$null)
if ($sz -match '(\d+)x(\d+)') {
    $w = [int]$Matches[1]
    $h = [int]$Matches[2]
}
$x  = [int]($w * 0.5)
$y1 = [int]($h * 0.94)
$y2 = [int]($h * 0.05)

# 4. hook_feed.js - heap-scan + scroll
& $adb shell su -c "rm -f $HEAP" 2>$null
$totalSwipes = $Cycles * $SwipesPerCycle
Step "Heap-scan: 1 injecao + $totalSwipes swipes..."

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName              = "frida"
$psi.Arguments             = "-U -q -p $apid -l `"$hookFeed`""
$psi.RedirectStandardInput = $true
$psi.UseShellExecute       = $false
$psi.CreateNoWindow        = $true
$proc = [System.Diagnostics.Process]::Start($psi)
Start-Sleep 4

for ($s = 1; $s -le $totalSwipes; $s++) {
    & $adb shell input swipe $x $y1 $x $y2 90 2>$null
    Start-Sleep -Milliseconds 100
    if (($s % 5) -eq 0) {
        Start-Sleep -Milliseconds 800
    }
    if (($s % 10) -eq 0) {
        $alive = (& $adb shell pidof $PKG 2>$null)
        if (-not $alive) { Write-Host "[!] app fechou."; break }
    }
}
Start-Sleep 4

try { $proc.StandardInput.Close() } catch { }
try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }

# 5. puxa heap
Step "Puxando heap_all.jsonl..."
& $adb shell su -c "cp $HEAP /sdcard/heap_all.jsonl; chmod 666 /sdcard/heap_all.jsonl" 2>$null
& $adb pull /sdcard/heap_all.jsonl "$HERE\heap_all.jsonl" 2>$null | Out-Null

$lines = Get-Content "$HERE\heap_all.jsonl" -ErrorAction SilentlyContinue
$capt = 0
if ($lines) { $capt = ($lines | Where-Object { $_ -ne '' }).Count }
if ($capt -eq 0) {
    Write-Host "[!] 0 entidades - feed nao estava visivel na tela." -ForegroundColor Yellow
    exit 1
}
Step "Heap-scan capturou $capt entidades de feed."

# 6. consolida
Write-Host ""
python "$HERE\consolidate.py" "$HERE" "$Lat" "$Lng" "$CityId"
Write-Host ""

# 7. envia pro Tinybird / Grafana
Step "Lat=$Lat  Lng=$Lng  CityId=$CityId  PointId=$PointId"
Step "HeapPath=$HERE\heap_all.jsonl  exists=$(Test-Path "$HERE\heap_all.jsonl")"
Step "Enviando pro Tinybird..."
& "$HERE\tinybird_send.ps1" -HeapPath "$HERE\heap_all.jsonl" -DeviceId $DeviceId -PointId $PointId -Lat $Lat -Lng $Lng -CityId $CityId -PoiId $PoiId
Step "tinybird_send concluido (exit=$LASTEXITCODE)"
