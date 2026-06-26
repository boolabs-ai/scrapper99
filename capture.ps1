<#
  capture.ps1 — CAPTURA pura de um ponto (chamada pelo crawler).

  NÃO abre o app nem navega/dispensa anúncios — isso é responsabilidade do CRAWLER
  (crawler/screen.py), que deixa o 99 já na aba Comida com o feed do ponto na tela.
  Aqui só: garante frida/SELinux -> loop (scroll + heap-scan hook_feed.js) -> pull
  heap_all.jsonl -> lê o POI real do AddressStorage (parse_address.py) -> consolidate.py
  -> tinybird_send.ps1.

  É o "lado scraper" reusado pelo crawler — mantém a captura separada da automação.
  (scrape.ps1 / scrape_pc.ps1 continuam intactos para uso standalone.)

  Uso (normalmente chamado pelo crawl_99.py):
    .\capture.ps1 -Lat -23.55 -Lng -46.63
    .\capture.ps1 -Lat -23.55 -Lng -46.63 -Cycles 8 -SwipesPerCycle 6 -DeviceId 99_food_app
#>
param(
    [Parameter(Mandatory = $true)][string]$Lat,
    [Parameter(Mandatory = $true)][string]$Lng,
    [string]$CityId          = '',
    [string]$PoiId           = '',
    [string]$PointId         = '',
    [string]$DeviceId        = '99_food_app',
    [int]$Cycles             = 8,
    [int]$SwipesPerCycle     = 6,
    [int]$ScanSeconds        = 10,
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'
$adb  = 'adb'
$PKG  = 'com.taxis99'
$HERE = $PSScriptRoot
$HEAP = "/data/data/$PKG/files/heap_all.jsonl"
function Step($m) { Write-Host "[capture] $m" -ForegroundColor DarkCyan }

# 1) device + permissive + fserver + forward (idempotente)
if ((& $adb get-state 2>$null) -ne 'device') { Write-Error "Device nao conectado."; exit 1 }
& $adb shell su -c "setenforce 0" 2>$null
if (-not (& $adb shell su -c "pidof fserver" 2>$null)) {
    & $adb shell su -c "nohup /data/local/tmp/fserver -l 0.0.0.0:2222 >/dev/null 2>&1 &" 2>$null
    Start-Sleep -Seconds 3
}
& $adb forward tcp:2222 tcp:2222 | Out-Null

# 2) o crawler garante o app na aba Comida; aqui só confirmamos o PID
$apid = "$(& $adb shell pidof $PKG 2>$null)".Trim()
if (-not $apid) { Write-Error "App $PKG nao esta rodando (o crawler deveria ter aberto)."; exit 1 }
Step "pid=$apid  ponto lat=$Lat lng=$Lng"

# 3) dimensoes p/ swipe
$w = 1080; $h = 2400
$size = (& $adb shell wm size 2>$null)
if ($size -match '(\d+)x(\d+)') { $w = [int]$Matches[1]; $h = [int]$Matches[2] }
$x = [int]($w * 0.5); $y1 = [int]($h * 0.72); $y2 = [int]($h * 0.28)

# 4) zera acumulador e roda loop scroll + heap-scan
& $adb shell su -c "rm -f $HEAP" 2>$null
Step "loop: $Cycles ciclos x $SwipesPerCycle swipes"
for ($c = 1; $c -le $Cycles; $c++) {
    for ($s = 1; $s -le $SwipesPerCycle; $s++) {
        & $adb shell input swipe $x $y1 $x $y2 450 2>$null
        Start-Sleep -Milliseconds 1000
    }
    $argline = '-H 127.0.0.1:2222 -q -p {0} -l "{1}\hook_feed.js"' -f $apid, $HERE
    $proc = Start-Process -FilePath "frida" -ArgumentList $argline -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds $ScanSeconds
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $n = (& $adb shell su -c "cat $HEAP 2>/dev/null | wc -l" 2>$null)
    Write-Host ("    ciclo {0}/{1} -> {2} entidades" -f $c, $Cycles, ("$n".Trim()))
    if (-not "$(& $adb shell pidof $PKG 2>$null)".Trim()) { Write-Host "[!] app fechou; parando."; break }
}

# 5) puxa heap
& $adb shell su -c "cp $HEAP /sdcard/heap_all.jsonl; chmod 666 /sdcard/heap_all.jsonl" 2>$null
& $adb pull /sdcard/heap_all.jsonl "$HERE\heap_all.jsonl" 2>$null | Out-Null

# 6) POI real do AddressStorage (poiId/cityId/city/addr) via parse_address.py
$City = ''; $AddressAll = ''; $Neighborhood = ''; $County = ''; $CountryCode = 'BR'
$tmpAddr = Join-Path $HERE '_addrstore.xml'
(& $adb shell su -c "cat '/data/data/$PKG/shared_prefs/com.didi.soda.address.manager.AddressStorage.xml'" 2>$null) -join "`n" | Set-Content -Path $tmpAddr -Encoding UTF8
$prevEnc = [Console]::OutputEncoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$poiJson = python "$HERE\parse_address.py" $tmpAddr 2>$null
[Console]::OutputEncoding = $prevEnc
if ($LASTEXITCODE -eq 0 -and $poiJson) {
    $poi = $poiJson | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($poi) {
        if (-not $PoiId)  { $PoiId  = "$($poi.poiId)" }
        if (-not $CityId) { $CityId = "$($poi.cityId)" }
        $City = "$($poi.city)"; $AddressAll = "$($poi.addressAll)"
        $Neighborhood = "$($poi.neighborhood)"; $County = "$($poi.county)"
        if ($poi.countryCode) { $CountryCode = "$($poi.countryCode)" }
        Step "POI real: poiId=$PoiId cityId=$CityId city=$City addr=$AddressAll"
    }
}
Remove-Item $tmpAddr -ErrorAction SilentlyContinue
if (-not $PointId) { $PointId = "${Lat}_${Lng}" }

# 7) consolida (grava point_lat/lng/cityId em cada loja)
python "$HERE\consolidate.py" "$HERE" "$Lat" "$Lng" "$CityId"

# 8) envia pro Tinybird
if ($DryRun) { Step "DRY-RUN: preview do payload (sem enviar)" }
else         { Step "enviando pro Tinybird..." }
& "$HERE\tinybird_send.ps1" -HeapPath "$HERE\heap_all.jsonl" -DeviceId $DeviceId `
    -PointId $PointId -Lat $Lat -Lng $Lng -CityId $CityId -PoiId $PoiId `
    -City $City -AddressAll $AddressAll -Neighborhood $Neighborhood -County $County `
    -CountryCode $CountryCode -DryRun:$DryRun
Step "concluido (exit=$LASTEXITCODE)"
