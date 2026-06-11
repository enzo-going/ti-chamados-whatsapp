---
tags: [helpdesk, demo, documentacao]
---

# Demonstração local — passo a passo

Como rodar o helpdesk completo na sua máquina, com **dados fake** e **sem
nenhuma dependência externa**: sem WhatsApp real, sem credenciais, sem rede —
o servidor escuta apenas em `127.0.0.1`.

Requisito único: **Python 3.10+** no PATH.

## Atalho (um comando)

No PowerShell, na raiz do projeto:

```powershell
.\demo.ps1
```

Isso cria o banco de demonstração (`demo.sqlite3`), sobe o servidor em uma
janela própria e abre o painel no navegador. Para encerrar, feche a janela do
servidor. Porta ocupada? `.\demo.ps1 -Port 8010`.

> Se o PowerShell bloquear o script por política de execução:
> `powershell -ExecutionPolicy Bypass -File .\demo.ps1`

## Passo a passo manual (os mesmos 3 comandos do script)

```powershell
# 1. Criar/recriar o banco de demonstração com 8 chamados fake
python -m helpdesk.demo seed --reset

# 2. Subir o servidor local (deixe rodando; Ctrl+C encerra)
python -m helpdesk.http_app --db demo.sqlite3

# 3. Abrir o painel (em outra janela, ou direto no navegador)
Start-Process "http://127.0.0.1:8000/dashboard"
```

O painel recarrega sozinho a cada 15 segundos.

## Simular mensagens chegando

Com o servidor rodando, em **outra** janela do PowerShell:

```powershell
# Mensagem nova -> abre chamado, com triagem e atribuição automáticas
python -m helpdesk.demo send "a impressora do RH parou de novo"

# Segunda mensagem do mesmo remetente -> follow-up: cai no MESMO chamado
python -m helpdesk.demo send "continua sem imprimir nada"

# Outro remetente -> chamado novo
python -m helpdesk.demo send "esqueci minha senha do sistema" --sender 5513990000042

# Mesmo evento entregue duas vezes -> idempotência: nada duplica
python -m helpdesk.demo send "teste de reentrega" --sender 5513990000043 --event-id evt-1
python -m helpdesk.demo send "teste de reentrega" --sender 5513990000043 --event-id evt-1
```

Após cada `send`, recarregue o painel (ou espere o auto-refresh) para ver o
efeito. O comando imprime o número do chamado e a categoria detectada.

## O que estou vendo?

- **`seed`** popula o banco passando pelo **fluxo real** do serviço: cada texto
  é triado por palavras-chave (categoria + prioridade), o chamado é atribuído a
  um atendente em rodízio e alguns avançam no ciclo de vida (em andamento,
  resolvido, fechado). Nada é inserido "por fora".
- **O painel** (`/dashboard`) lista só os chamados **em aberto** (aberto,
  atribuído, em andamento), ordenados por prioridade e idade. Ele recebe uma
  **projeção restrita**: número, categoria, prioridade, status, responsável,
  horário de abertura e tempo em aberto. Telefone, nome do solicitante e texto
  das mensagens ficam fora por construção (há testes garantindo).
- **`send`** envia um payload JSON ao `POST /inbound` — a mesma entrada que uma
  integração real usaria. Por isso a demonstração exibe os comportamentos
  centrais: triagem, rodízio, follow-up (mesma pessoa, mesmo problema → mesmo
  chamado) e idempotência (reentrega do mesmo evento → nada duplica).

## Recomeçar do zero

```powershell
python -m helpdesk.demo seed --reset
```

(O servidor pode ficar rodando; o banco é recriado e o painel passa a mostrar
o estado novo no próximo refresh.)

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `send` diz "O servidor local não está respondendo" | servidor não está rodando, ou está em outra porta | suba o passo 2; o `--port` do `send` precisa ser o mesmo do servidor |
| `demo.ps1` avisa que a porta já está em uso | a janela de uma demo anterior continua aberta | feche a janela antiga e rode de novo, ou `.\demo.ps1 -Port 8010` |
| `O arquivo demo.sqlite3 já existe` | seed sem `--reset` | acrescente `--reset` |
| Painel vazio | banco sem chamados em aberto | rode o seed de novo ou envie um `send` |

Pode deixar o painel aberto no navegador à vontade: o servidor atende várias
conexões ao mesmo tempo (navegador + `send` + refresh) sem travar.

> **Escopo:** demonstração de desenvolvimento. O servidor não deve ser exposto
> para fora de `127.0.0.1`; não há autenticação porque nada sai da máquina.

Ver também: [roteiro de demonstração](roteiro-demo.md) ·
[arquitetura](arquitetura.md) · [decisões](decisoes.md)
