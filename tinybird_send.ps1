<#
  tinybird_send.ps1 — envia as paginas do feed (heap_all.jsonl) para o Tinybird.

  Cada linha do heap_all.jsonl e' uma HomeFeedEntity serializada (JSON cru do app).
  Aqui montamos o envelope minimo que o MV do Tinybird espera (event_type=api_request,
  request_url contendo feed/indexV3, response_body com errno=0 e o feed dentro de data.feed).

  As materialized views ninenine_feed_shops / ninenine_feed_summary expandem as lojas
  a partir desse envelope e alimentam o Grafana.

  Uso:
    .\tinybird_send.ps1                         # le heap_all.jsonl do mesmo diretorio
    .\tinybird_send.ps1 -Lat -30.0277 -Lng -51.2287 -CityId 4501
    .\tinybird_send.ps1 -HeapPath outro.jsonl -DeviceId meu_device
#>
param(
    [string]$HeapPath = '',
    [string]$DeviceId = '99_food_app',
    [string]$PointId  = '',
    [string]$Lat      = '',
    [string]$Lng      = '',
    [string]$CityId   = '',
    [string]$PoiId    = ''
)

$TINYBIRD_URL   = 'https://api.us-east.aws.tinybird.co/v0/events?name=ninenine_events'
$TINYBIRD_TOKEN = 'p.eyJ1IjogImY4MjUwMWZiLWMzMWYtNDQxMC05NDQ0LWQxYmNiNzIyNGJmOCIsICJpZCI6ICIzMjI0ODM1My1hNzM2LTRlNWUtYWIzYy04OGNjZTM2YjUzOWEiLCAiaG9zdCI6ICJ1cy1lYXN0LWF3cyJ9.sQCpVZN7tj37b6s9SI_Je3uUT9xE0eXx0MfQgyLRhYM'
$USER_AGENT     = 'insomnia/11.5.0'
$HERE           = $PSScriptRoot

if (-not $HeapPath) { $HeapPath = Join-Path $HERE 'heap_all.jsonl' }
if (-not (Test-Path $HeapPath)) {
    Write-Host "[!] Arquivo nao encontrado: $HeapPath" -ForegroundColor Yellow; exit 1
}

# se PointId nao foi passado, monta a partir de Lat_Lng
if (-not $PointId -and $Lat -and $Lng) { $PointId = "${Lat}_${Lng}" }
if (-not $PoiId) { $PoiId = $PointId }

$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
if (-not $curl) { $curl = "$env:SystemRoot\System32\curl.exe" }
if (-not (Test-Path $curl)) { Write-Host "[!] curl.exe nao encontrado." -ForegroundColor Red; exit 1 }

# le paginas, tira vazias e dedup exato (setInterval repete linhas)
$raw   = [System.IO.File]::ReadAllLines($HeapPath, [System.Text.Encoding]::UTF8)
$feeds = [System.Collections.Generic.List[string]]::new()
$seen  = [System.Collections.Generic.HashSet[string]]::new()
foreach ($l in $raw) {
    $t = $l.Trim()
    if ($t.Length -gt 0 -and $seen.Add($t)) { [void]$feeds.Add($t) }
}
if ($feeds.Count -eq 0) { Write-Host "[!] Nenhuma pagina de feed em $HeapPath" -ForegroundColor Yellow; exit 0 }

# poi: objeto de localizacao embutido no response_body
$poiJson = ([ordered]@{ poiId = $PoiId; lat = $Lat; lng = $Lng; cityId = $CityId } | ConvertTo-Json -Compress)

Write-Host (">> Enviando {0} paginas  device={1}  lat={2}  lng={3}  cityId={4}" -f $feeds.Count, $DeviceId, $Lat, $Lng, $CityId) -ForegroundColor Cyan

$tmp  = Join-Path $env:TEMP ("tb_99_" + $PID + ".json")
$utf8 = New-Object System.Text.UTF8Encoding($false)
$ok = 0; $fail = 0; $i = 0

foreach ($feedRaw in $feeds) {
    $i++
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")

    # response_body: envelope minimo + feed cru da heap (sem re-serializar)
    $responseBody = '{"errno":"0","errmsg":"","data":{"address":{"addressInfo":{"address":{"poi":' `
                  + $poiJson + '}}},"feed":' + $feedRaw + '}}'

    $eventData = [ordered]@{
        request_url          = 'https://c.didi-food.com/feed/indexV3'
        request_method       = 'POST'
        request_headers      = [ordered]@{ 'User-Agent' = 'okhttp/4.12.0'; 'TripCountry' = 'BR' }
        request_body         = "page=0&count=100&lat=$Lat&lng=$Lng&poiLat=$Lat&poiLng=$Lng&cityId=$CityId&poiCityId=$CityId&poiId=$PoiId"
        response_status_code = 200
        response_headers     = [ordered]@{ 'content-type' = 'application/json' }
        response_body        = $responseBody
        request_timestamp    = $ts
        response_timestamp   = $ts
        success              = $true
        errno                = 0
        error_message        = 'ok'
    }

    $payload = [ordered]@{
        event_type = 'api_request'
        device_id  = $DeviceId
        point_id   = $PointId
        event_data = $eventData
    } | ConvertTo-Json -Depth 12 -Compress

    [System.IO.File]::WriteAllText($tmp, $payload, $utf8)

    $lines = @(& $curl -sS -w "`n%{http_code}" $TINYBIRD_URL `
        -H "Authorization: Bearer $TINYBIRD_TOKEN" `
        -H "Content-Type: application/json" `
        -H "User-Agent: $USER_AGENT" `
        --data-binary "@$tmp" 2>&1)

    $code  = "$($lines[-1])".Trim()
    $body  = if ($lines.Count -gt 1) { $lines[0..($lines.Count-2)] -join ' ' } else { '' }

    if ($code -match '^2\d\d$') {
        $ok++
        Write-Host ("  [ok {0}] pagina {1}/{2} ({3} bytes)" -f $code, $i, $feeds.Count, $feedRaw.Length)
    } else {
        $fail++
        Write-Host ("  [ERRO {0}] pagina {1}/{2} -> {3}" -f $code, $i, $feeds.Count, $body) -ForegroundColor Yellow
    }
}

Remove-Item $tmp -ErrorAction SilentlyContinue
Write-Host (">> Concluido: {0} ok, {1} erro." -f $ok, $fail) -ForegroundColor Cyan
