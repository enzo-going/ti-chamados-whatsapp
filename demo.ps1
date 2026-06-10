# Demonstração local do helpdesk em um comando.
#
#   .\demo.ps1            # cria o banco fake, sobe o servidor e abre o painel
#   .\demo.ps1 -Port 8010 # idem, em outra porta
#
# Tudo é fake e local (127.0.0.1): sem WhatsApp real, sem credenciais.
# O servidor abre em uma janela própria — feche-a (ou Ctrl+C nela) para encerrar.
# Passo a passo manual e explicações: docs/demo-local.md

param([int]$Port = 8000)

python -m helpdesk.demo seed --db demo.sqlite3 --reset
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Start-Process python -ArgumentList "-m", "helpdesk.http_app", "--db", "demo.sqlite3", "--port", "$Port"
Start-Sleep -Seconds 1
Start-Process "http://127.0.0.1:$Port/dashboard"

Write-Host ""
Write-Host "Painel aberto em:  http://127.0.0.1:$Port/dashboard"
Write-Host "Simular mensagem:  python -m helpdesk.demo send `"a impressora do RH parou`" --port $Port"
Write-Host "Encerrar:          feche a janela do servidor."
