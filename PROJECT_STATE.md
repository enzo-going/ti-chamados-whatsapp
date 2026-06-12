# Estado do projeto

Snapshot operacional para retomar o trabalho em qualquer máquina. Detalhes
vivos ficam em [`docs/`](docs/index.md) — este arquivo aponta para eles e
concentra estado, comandos e checklist do dia a dia.

## Estado atual

- **Branch:** `main` (sincronizada com `origin/main`).
- **Suíte de testes:** 167 testes (unittest), todos verdes.
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
- Checagem segura da configuração (`python -m helpdesk.config check`): valida
  banco e quadro sem efeitos colaterais e reporta as variáveis reservadas da
  integração apenas como definida/não definida (valores nunca aparecem).
- Preparação de pré-integração sem segredos: `.env.example` (somente nomes de
  variáveis) e checklist técnico em [docs/pre-integracao.md](docs/pre-integracao.md).
- Borda local da Cloud API (`helpdesk/whatsapp.py`), testada sem rede:
  handshake de verificação do webhook, validação de assinatura HMAC-SHA256,
  parser do payload de webhook → payload neutro do `/inbound` (id da mensagem
  = `event_id`, idempotência aproveitada) e `CloudApiTransport` de envio com
  HTTP injetável (token nunca aparece em `repr`/erros). Rotas `/webhook` no
  servidor local, fechadas (503) sem configuração.

## Arquivos principais

| Caminho | Responsabilidade |
|---|---|
| `helpdesk/models.py` | Entidades de domínio (`Ticket`, `Message`, `Attendant`, enums) |
| `helpdesk/triage.py` | Classificação por palavras-chave (categoria + prioridade) |
| `helpdesk/attendants.py` | Quadro de atendentes configurável (JSON local) |
| `helpdesk/repository.py` | Armazenamento em memória (testes/demo) + SQLite (persistente) |
| `helpdesk/inbound.py` | Entrada: payload neutro → `Message`, com idempotência |
| `helpdesk/whatsapp.py` | Borda da Cloud API: webhook (verificação + assinatura), parser e envio |
| `helpdesk/service.py` | Orquestra o fluxo completo |
| `helpdesk/http_app.py` | Servidor HTTP local (`127.0.0.1`): entrada + painel + `/webhook` |
| `helpdesk/dashboard.py` | Painel somente leitura: projeção restrita + HTML |
| `helpdesk/demo.py` | Demonstração: seed fake, simulação de mensagens e `check` |
| `helpdesk/config.py` | Caminhos (banco, quadro) via variáveis de ambiente |
| `main.py` | Demonstração de linha de comando (`--repl`, `--db`) |
| `demo.ps1` | Demonstração completa em um comando (Windows) |
| `tests/` | Suíte de testes (unittest) |

### Alterações recentes mais relevantes

- `helpdesk/whatsapp.py` (novo): borda local da Cloud API — verificação do
  webhook, assinatura HMAC-SHA256 (fail closed), parser do payload para o
  formato do `/inbound` e `CloudApiTransport` com HTTP injetável.
- `helpdesk/http_app.py`: rotas `GET/POST /webhook` (503 sem configuração;
  403 sem assinatura válida) e flag `--transport fake|cloud-api` (a opção
  `cloud-api` exige as variáveis de ambiente e só é usada na validação
  supervisionada).
- `helpdesk/config.py`: accessors das variáveis da integração
  (`whatsapp_token()` etc.) — valores continuam nunca aparecendo em saída.
- `tests/test_whatsapp.py`: 32 testes — handshake, assinatura, parser
  (status/tipos ignorados sem vazar conteúdo), idempotência por id de
  mensagem, transporte sem rede e token fora de `repr`/erros, rotas de ponta
  a ponta em porta efêmera.
- `docs/pre-integracao.md`: seção da borda implementada + roteiro do dia da
  validação com número de teste.

## Pendências técnicas

- **Fase 3 — integração de mensagens (Cloud API):** borda local pronta e
  testada sem rede (`helpdesk/whatsapp.py`); **a conexão real continua
  bloqueada** pela decisão da estratégia do número. Roteiro do dia da
  validação em [docs/pre-integracao.md](docs/pre-integracao.md).
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

# Diagnóstico seguro da configuração local (não exibe valores de variáveis)
python -m helpdesk.config check

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
