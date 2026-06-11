# Estado do projeto

Snapshot operacional para retomar o trabalho em qualquer máquina. Detalhes
vivos ficam em [`docs/`](docs/index.md) — este arquivo aponta para eles e
concentra os comandos do dia a dia.

## O que é

Núcleo de helpdesk de TI que transforma mensagens (futuramente de WhatsApp)
em chamados: triagem automática por palavras-chave, atribuição em rodízio
entre atendentes ativos, follow-up sem duplicação, idempotência de eventos,
persistência SQLite e painel local somente leitura. Python 3.10+ puro, zero
dependências de runtime.

## O que funciona hoje

- Fluxo completo de chamados: criação, triagem (categoria + prioridade),
  atribuição, follow-up, reabertura, ciclo de vida (ver [arquitetura](docs/arquitetura.md)).
- Persistência SQLite com idempotência de eventos (`processed_events`).
- Entrada HTTP local em `127.0.0.1` (`POST /inbound`, payload JSON neutro).
- Painel somente leitura em `/dashboard` (projeção restrita; sem telefone,
  nomes de solicitantes ou texto de mensagens).
- Quadro de atendentes configurável por JSON local (`HELPDESK_ATTENDANTS_PATH`),
  com papéis e ativo/inativo; só ativos entram no rodízio.
- Modo de demonstração: seed de chamados fake + simulação de mensagens
  ([passo a passo](docs/demo-local.md) · [roteiro de apresentação](docs/roteiro-demo.md)).
- Checagem automática da demo (`python -m helpdesk.demo check` ou
  `.\demo.ps1 -Check`): percorre o fluxo completo em ambiente descartável e
  aponta o passo que falhar — pré-voo de apresentações.
- Suíte com 121 testes (unittest); CI em Python 3.10/3.11/3.12.

## O que está pendente / próximos passos

Decisões registradas no [roadmap](docs/roadmap.md) e nas [decisões](docs/decisoes.md):

- **Fase 3 — integração WhatsApp (Cloud API):** bloqueada pela decisão da
  estratégia do número. Nenhuma integração real conectada, por escolha.
- **Fase 4 — interface dos atendentes:** painel web interativo ou comandos;
  aguardando definição.
- **Fase 5 — observabilidade:** métricas, notificação de prioridade alta.
- **Wallboard (TV):** painel atual é a base; exposição na rede interna e
  acesso controlado ficam para quando o requisito for confirmado.
- Deferido de propósito: persistência do ponteiro do round-robin (decisões 5 e 11).

## Comandos úteis

```powershell
# Testes (devem ficar todos verdes)
python -m unittest discover -s tests

# Pré-voo da demo: o fluxo completo funciona nesta máquina?
python -m helpdesk.demo check

# Demonstração completa em um comando (Windows)
.\demo.ps1

# Peças da demo, na mão
python -m helpdesk.demo seed --reset                    # banco fake demo.sqlite3
python -m helpdesk.http_app --db demo.sqlite3           # servidor local
python -m helpdesk.demo send "a impressora parou"       # simula mensagem
# painel: http://127.0.0.1:8000/dashboard

# Demonstração CLI simples (sem servidor)
python main.py            # roteiro de exemplo
python main.py --repl     # interativo
```

## Convenções de trabalho

- `main` é protegida (checks obrigatórios em 3.10/3.11/3.12): todo trabalho
  entra por branch + PR com CI verde.
- Repositório público: dados sempre fictícios e genéricos — sem nomes reais,
  telefones reais, credenciais, `.env` ou bancos locais (já ignorados).
- Documentação técnica e neutra em `docs/` (índice em [docs/index.md](docs/index.md)).
