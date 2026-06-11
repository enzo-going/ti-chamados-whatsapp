# Demonstração local do helpdesk em um comando.
#
#   .\demo.ps1            # cria o banco fake, sobe o servidor e abre o painel
#   .\demo.ps1 -Port 8010 # idem, em outra porta
#   .\demo.ps1 -Check     # só checa se está tudo pronto (nada fica rodando)
#
# Tudo é fake e local (127.0.0.1): sem WhatsApp real, sem credenciais.
# O servidor abre em uma janela própria — feche-a (ou Ctrl+C nela) para encerrar.
# Passo a passo manual e explicações: docs/demo-local.md

param([int]$Port = 8000, [switch]$Check)

# Pré-voo: percorre o fluxo completo em ambiente descartável e sai.
if ($Check) {
    python -m helpdesk.demo check
    exit $LASTEXITCODE
}

# Porta já em uso? Provavelmente a janela de uma demo anterior continua aberta.
$emUso = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($emUso) {
    Write-Host "A porta $Port já está em uso — provavelmente uma demo anterior ainda está rodando."
    Write-Host "Feche a janela antiga do servidor e rode de novo, ou use outra porta:"
    Write-Host "    .\demo.ps1 -Port 8010"
    exit 1
}

python -m helpdesk.demo seed --db demo.sqlite3 --reset
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Start-Process python -ArgumentList "-m", "helpdesk.http_app", "--db", "demo.sqlite3", "--port", "$Port"

# Espera o servidor responder (até ~5s) antes de abrir o navegador.
$pronto = $false
foreach ($tentativa in 1..10) {
    Start-Sleep -Milliseconds 500
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        $pronto = $true
        break
    } catch { }
}
if (-not $pronto) {
    Write-Host "O servidor não respondeu na porta $Port. Veja o erro na janela do servidor."
    exit 1
}

Start-Process "http://127.0.0.1:$Port/dashboard"

Write-Host ""
Write-Host "Painel aberto em:  http://127.0.0.1:$Port/dashboard"
Write-Host "Simular mensagem:  python -m helpdesk.demo send `"a impressora do RH parou`" --port $Port"
Write-Host "Encerrar:          feche a janela do servidor."
