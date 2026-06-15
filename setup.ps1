<#
  setup.ps1 — configuracao de PRIMEIRA VEZ do scraper do 99 Food.

  Faz:
    1. Confere device (adb) e arquitetura (espera arm64-v8a).
    2. Baixa frida-server 17.6.1 (android-arm64) e instala no device como /data/local/tmp/fserver
       (renomeado de proposito: o anti-tamper procura o processo "frida-server").
    3. Alinha o frida do PC para 17.6.1 (cliente e server PRECISAM bater).
    4. Verifica que o frida do PC conecta no fserver do device.

  VERSAO CRITICA: frida 17.6.1.  Com 17.9.x o app 99 detecta e MATA o processo (~1 min).

  Pre-requisitos (NAO automatizados — ver README):
    - Device Android arm64 com ROOT (KernelSU testado) e su funcional.
    - adb (platform-tools) no PATH.
    - Python 3 + pip no PATH.
  Uso:  .\setup.ps1
#>
$ErrorActionPreference = 'Stop'
$adb = 'adb'
$FRIDA_VER = '17.6.1'
$HERE = $PSScriptRoot
function Step($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }

# 1) device
$state = (& $adb get-state 2>$null)
if ($state -ne 'device') { throw "Device nao conectado/autorizado (adb get-state = '$state'). Conecte por USB e autorize." }
$abi = (& $adb shell getprop ro.product.cpu.abi 2>$null).Trim()
Step "Device OK | ABI = $abi"
if ($abi -ne 'arm64-v8a') { Warn "ABI != arm64-v8a. Ajuste a URL do frida-server para a ABI correta." }

# 2) confere root
$who = (& $adb shell su -c "id -u" 2>$null).Trim()
if ($who -ne '0') { throw "Sem root (su -c id -u retornou '$who'). Este metodo exige root." }
Ok "Root OK"

# 3) baixa frida-server 17.6.1 arm64
$xz = Join-Path $HERE "frida-server-$FRIDA_VER-android-arm64.xz"
$bin = Join-Path $HERE "fserver"
if (-not (Test-Path $bin)) {
    if (-not (Test-Path $xz)) {
        Step "Baixando frida-server $FRIDA_VER (android-arm64)..."
        $url = "https://github.com/frida/frida/releases/download/$FRIDA_VER/frida-server-$FRIDA_VER-android-arm64.xz"
        Invoke-WebRequest -Uri $url -OutFile $xz -Headers @{ 'User-Agent' = 'ps' }
        Ok "Baixado ($([math]::Round((Get-Item $xz).Length/1MB,1)) MB)"
    }
    Step "Descompactando (.xz -> fserver)..."
    python -c "import lzma,shutil; shutil.copyfileobj(lzma.open(r'$xz'), open(r'$bin','wb'))"
    Ok "fserver pronto"
}

# 4) instala fserver no device
Step "Instalando fserver em /data/local/tmp/ ..."
& $adb push $bin /data/local/tmp/fserver | Out-Null
& $adb shell su -c "chmod 755 /data/local/tmp/fserver"
Ok "fserver instalado no device"

# 5) alinha frida do PC para 17.6.1
$pcver = (& frida --version 2>$null)
if ($pcver -ne $FRIDA_VER) {
    Step "Alinhando frida do PC: $pcver -> $FRIDA_VER ..."
    python -m pip install --force-reinstall --no-deps "frida==$FRIDA_VER" 2>&1 | Select-Object -Last 1
    $pcver = (& frida --version 2>$null)
}
if ($pcver -ne $FRIDA_VER) { Warn "frida do PC = $pcver (esperado $FRIDA_VER). Cliente/server precisam bater." } else { Ok "frida PC = $FRIDA_VER" }

# 6) teste de conexao
Step "Testando fserver + conexao frida..."
& $adb shell su -c "pkill fserver" 2>$null
& $adb shell su -c "setenforce 0" 2>$null
& $adb shell su -c "nohup /data/local/tmp/fserver -l 0.0.0.0:2222 >/dev/null 2>&1 &" 2>$null
Start-Sleep -Seconds 3
& $adb forward tcp:2222 tcp:2222 | Out-Null
$ps = (& frida-ps -H 127.0.0.1:2222 2>&1 | Select-String 'PID' | Measure-Object).Count
if ($ps -ge 1) { Ok "frida conecta no device (porta 2222). SETUP COMPLETO." }
else { Warn "frida nao conectou. Confira: setenforce 0, fserver rodando, adb forward 2222." }

Write-Host ""
Write-Host "Proximo passo: abra o app 99 -> aba Comida (lista de restaurantes) -> rode  .\scrape.ps1" -ForegroundColor White
