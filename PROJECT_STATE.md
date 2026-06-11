# Estado do projeto

Snapshot operacional para retomar o trabalho em qualquer máquina. Detalhes
vivos ficam em [`docs/`](docs/index.md) — este arquivo aponta para eles e
concentra estado, comandos e checklist do dia a dia.

## Estado atual

- **Branch:** `main` (sincronizada com `origin/main`).
- **Suíte de testes:** 121 testes (unittest), todos verdes.
- **CI:** GitHub Actions em Python 3.10 / 3.11 / 3.12.
- **Working tree:** limpo, sem pendências de feature em aberto.
- **Runtime:** Python 3.10+ puro, zero dependências externas.

## O que é

Núcleo de helpdesk de TI que transforma mensagens (futuramente de WhatsApp)
em chamados: triagem automática por palavras-chave, atribuição em rodízio
entre atendentes ativos, follow-up sem duplicação, idempotência de eventos,
persistência SQLite e painel local somente leitura.

## Objetivo atual

Fase ativa de **uso, visualização, teste e demonstração** local. A prioridade
é deixar o sistema fácil de rodar, entender e apresentar, simulando com
segurança o que futuramente virá da integração de mensagens: entrada,
triagem, criação de chamado, persistência, follow-up, idempotência e painel.

## Funcionalidades já implementadas

- Fluxo completo de chamados: criação, triagem (categoria + prioridade),
  atribuição, follow-up, reabertura e ciclo de vida (ver
  [arquitetura](docs/arquitetura.md)).
- Persistência SQLite com idempotência de eventos (`processed_events`).
- Entrada HTTP local em `127.0.0.1` (`POST /inbound`, payload JSON neutro).
- Painel somente leitura em `/dashboard` (projeção restrita; sem telefone,
  nomes de solicitantes ou texto de mensagens).
- Quadro de atendentes configurável por JSON local (`HELPDESK_ATTENDANTS_PATH`),
  com papéis e ativo/inativo; só ativos entram no rodízio.
- Modo de demonstração: seed de chamados fake + simulação de mensagens
  ([passo a passo](docs/demo-local.md) · [roteiro](docs/roteiro-demo.md)).
- Checagem automática da demonstração (`python -m helpdesk.demo check` ou
  `.\demo.ps1 -Check`): percorre o fluxo completo em ambiente descartável
  (banco temporário + porta efêmera) e aponta o passo que falhar.

## Arquivos principais

| Caminho | Responsabilidade |
|---|---|
| `helpdesk/models.py` | Entidades de domínio (`Ticket`, `Message`, `Attendant`, enums) |
| `helpdesk/triage.py` | Classificação por palavras-chave (categoria + prioridade) |
| `helpdesk/attendants.py` | Quadro de atendentes configurável (JSON local) |
| `helpdesk/repository.py` | Armazenamento em memória (testes/demo) + SQLite (persistente) |
| `helpdesk/inbound.py` | Entrada: payload neutro → `Message`, com idempotência |
| `helpdesk/service.py` | Orquestra o fluxo completo |
| `helpdesk/http_app.py` | Servidor HTTP local (`127.0.0.1`): entrada + painel |
| `helpdesk/dashboard.py` | Painel somente leitura: projeção restrita + HTML |
| `helpdesk/demo.py` | Demonstração: seed fake, simulação de mensagens e `check` |
| `helpdesk/config.py` | Caminhos (banco, quadro) via variáveis de ambiente |
| `main.py` | Demonstração de linha de comando (`--repl`, `--db`) |
| `demo.ps1` | Demonstração completa em um comando (Windows) |
| `tests/` | Suíte de testes (unittest) |

### Alterações recentes mais relevantes

- `helpdesk/demo.py`: subcomando `check` (pré-voo do fluxo completo).
- `demo.ps1`: opção `-Check`; arquivo gravado em UTF-8 com BOM para parsear
  no Windows PowerShell 5.1.
- `tests/test_demo.py`: cobertura da checagem (sucesso, caminho de falha e
  garantia de não tocar no banco padrão).
- `docs/` e `README.md`: documentação da checagem automática.

## Pendências técnicas

- **Fase 3 — integração de mensagens (Cloud API):** bloqueada pela decisão da
  estratégia do número. Nenhuma integração real conectada, por escolha.
- **Fase 4 — interface dos atendentes:** painel interativo ou comandos;
  aguardando definição.
- **Fase 5 — observabilidade:** métricas, notificação de prioridade alta.
- **Wallboard (TV):** o painel atual é a base; exposição na rede interna e
  acesso controlado ficam para quando o requisito for confirmado.
- Deferido de propósito: persistência do ponteiro do round-robin
  (ver [decisões](docs/decisoes.md), decisões 5 e 11).

## Próximos passos recomendados

Frente sem bloqueio, com foco em demonstração:

1. **Enriquecer o painel `/dashboard`** para o cenário da TV: resumo por
   categoria e por atendente, e destaque visual para chamados com tempo em
   aberto excessivo — mantendo a projeção restrita (sem telefone, nome de
   solicitante ou texto das mensagens).
2. **Alternativa menor:** um modo de roteiro que dispare a sequência de
   mensagens da apresentação automaticamente.

Ambos rodam local e não dependem das Fases 3/4 (bloqueadas por decisão).

## Como rodar o projeto

```powershell
# Demonstração completa em um comando (Windows)
.\demo.ps1                                   # cria banco fake, sobe servidor, abre painel
.\demo.ps1 -Port 8010                        # em outra porta

# Peças da demonstração, na mão
python -m helpdesk.demo seed --reset         # banco fake demo.sqlite3
python -m helpdesk.http_app --db demo.sqlite3   # servidor local (Ctrl+C encerra)
python -m helpdesk.demo send "a impressora parou"   # simula mensagem
# painel: http://127.0.0.1:8000/dashboard

# Demonstração CLI simples (sem servidor)
python main.py                               # roteiro de exemplo
python main.py --repl                        # interativo
python main.py --db chamados.sqlite3         # persistindo em SQLite
```

## Comandos de teste / verificação

```powershell
# Suíte completa (deve ficar toda verde)
python -m unittest discover -s tests

# Pré-voo da demonstração: o fluxo completo funciona nesta máquina?
python -m helpdesk.demo check                # ou: .\demo.ps1 -Check
```

Não há etapa de build: o projeto é Python puro, sem dependências de runtime
(ver `requirements.txt`).

## Riscos conhecidos

- **Fim de linha (CRLF/LF) no Windows:** o git pode sinalizar `README.md` e
  outros arquivos como modificados apenas por conversão de fim de linha.
  Confirmar com `git diff` antes de commitar; descartar com `git restore`
  quando o diff de conteúdo for vazio.
- **Scripts `.ps1` precisam de UTF-8 com BOM:** o Windows PowerShell 5.1 lê
  `.ps1` sem BOM como ANSI e pode falhar no parse de caracteres acentuados.
  Manter `demo.ps1` com BOM.
- **Política de execução do PowerShell:** se `.\demo.ps1` for bloqueado, usar
  `powershell -ExecutionPolicy Bypass -File .\demo.ps1`.
- **Porta ocupada:** uma demonstração anterior ainda aberta segura a porta;
  fechar a janela do servidor ou usar `-Port`.
- **Escopo local:** o servidor só deve escutar em `127.0.0.1`, sem
  autenticação. Não expor para fora da máquina nesta fase.

## Convenções de trabalho

- `main` é protegida (checks obrigatórios em 3.10/3.11/3.12): trabalho de
  feature entra por branch + PR com CI verde.
- Repositório público: dados sempre fictícios e genéricos — sem nomes reais,
  telefones reais, credenciais, `.env` ou bancos locais (já ignorados).
- Documentação técnica e neutra em `docs/` (índice em
  [docs/index.md](docs/index.md)).

## Checklist para continuar em outro PC

1. `git clone https://github.com/enzo-going/ti-chamados-whatsapp.git` (se ainda
   não tiver o repositório) e entrar na pasta.
2. `git checkout main` e `git pull origin main`.
3. Conferir que há Python 3.10+ no PATH: `python --version`.
4. Rodar a suíte: `python -m unittest discover -s tests` (esperado: tudo verde).
5. Rodar o pré-voo: `python -m helpdesk.demo check` (esperado: todos os passos
   `[ok]`).
6. Subir a demonstração: `.\demo.ps1` e abrir o painel em
   `http://127.0.0.1:8000/dashboard`.
7. (Opcional) Quadro de atendentes próprio: copiar `atendentes.exemplo.json`
   para `atendentes.json` (não versionado) e apontar `HELPDESK_ATTENDANTS_PATH`.
