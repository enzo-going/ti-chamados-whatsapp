---
tags: [helpdesk, roadmap]
---

# Roadmap — protótipo → MVP

Documento vivo do plano incremental para transformar o protótipo em um MVP real
de helpdesk de TI por WhatsApp. Atualizado a cada fase.

## Legenda de status

- ✅ concluído  ·  🔜 próximo  ·  ⏳ planejado  ·  ⛔ bloqueado por decisão sua

## Visão geral das fases

| Fase | Objetivo | Status |
|---|---|---|
| 0 | Fundação: config via env + logging | ✅ (config na Fase 1; logging operacional na borda) |
| **1** | **Persistência SQLite** | **✅ concluída em 2026-06-08** |
| 2 | Entrada HTTP local + idempotência + follow-up de chamado aberto | ✅ parte local concluída |
| 3 | Integração WhatsApp Cloud API (envio + segurança do webhook) | 🟡 borda local pronta · conexão ⛔ depende da decisão do número |
| 4 | Interface para atendentes (painel web ou comandos) | ⛔ depende da sua escolha |
| 5 | Observabilidade: métricas, notificação de prioridade alta, auditoria | 🟡 início: log operacional na borda |

## Fase 1 — Persistência SQLite ✅

**Objetivo:** trocar a persistência só-em-memória por SQLite testável, mantendo a
arquitetura e sem quebrar os testes existentes.

**Entregue:**

- `SqliteTicketRepository` em `helpdesk/repository.py`, satisfazendo o `Protocol`
  `TicketRepository` — o `HelpdeskService` não mudou de contrato.
- `helpdesk/config.py`: caminho do banco via `HELPDESK_DB_PATH` (sem segredos no
  código).
- `main.py --db [ARQUIVO]`: roda a demo persistindo em SQLite; sem a flag,
  continua em memória (efêmero).
- Contrato `TicketRepository` ganhou `update()`/`all()`; o serviço faz write-back
  após cada mutação (ver [decisões](decisoes.md), decisão 5).
- 12 testes novos (contrato, persistência entre conexões, round-trip de
  datetime/assignee/histórico, integração com o serviço). **Suíte: 38 verdes.**

**Como verificar:**

```bash
python -m unittest discover -s tests        # suíte completa
python main.py --db chamados.sqlite3         # roda; rode 2x: os IDs continuam
```

**Deferido (decisão consciente):** persistência do estado de rodízio
(`round-robin`) — ver [decisões](decisoes.md).

## Fase 2 — Entrada HTTP local + idempotência ✅ (parte local)

**Entregue (tudo local e sem integração externa):**

- `helpdesk/inbound.py`: payload JSON neutro → `Message` (`parse_payload`) e
  `MessageGateway` com **idempotência** por `event_id`.
- `helpdesk/repository.py`: tabela `processed_events` + `seen_event()`/
  `record_event()`; idempotência **persistente** no SQLite (schema v2).
- `helpdesk/http_app.py`: servidor HTTP **local** (`127.0.0.1`) da biblioteca
  padrão, para exercitar a entrada de ponta a ponta com payloads próprios.
- **Follow-up em chamado aberto:** uma nova mensagem do mesmo remetente, dentro
  da janela de continuidade, é anexada ao chamado aberto em vez de abrir outro
  (ver [decisões](decisoes.md), decisão 9).
- Testes: parsing, idempotência (memória e SQLite, inclusive após reabrir o
  banco), HTTP local em porta efêmera e follow-up.

**Evolução:** a borda real de entrada e saída (Cloud API) já foi **implementada
e testada sem rede** na Fase 3 abaixo; falta apenas a **conexão real**, que
depende da decisão do número.

**Fora de escopo (continua valendo):** sem **conexão real** ao WhatsApp/Cloud
API, sem webhook público exposto, sem credenciais — o código da borda existe,
mas nada se conecta a uma conta real sem aprovação.

## Fases 3–5 — resumo

- **3. WhatsApp Cloud API:** a **borda local está pronta** —
  `helpdesk/whatsapp.py` implementa o handshake de verificação do webhook, a
  validação de assinatura (HMAC-SHA256), o parser do payload de webhook para
  o formato neutro do `/inbound` (id da mensagem = `event_id`, aproveitando a
  idempotência persistida) e o `CloudApiTransport` de envio com HTTP
  injetável (testado sem rede). As rotas `/webhook` do servidor local ficam
  fechadas (503) sem `WHATSAPP_VERIFY_TOKEN`/`WHATSAPP_APP_SECRET`. **A
  conexão real continua bloqueada** até decidir a estratégia do número (ver
  abaixo); o roteiro do dia da validação está em
  [pre-integracao](pre-integracao.md).
- **4. Atendentes:** painel web mínimo *ou* comandos por WhatsApp. Depende da sua
  escolha.
- **5. Observabilidade:** métricas, notificação de prioridade alta, logs de
  auditoria.

## Wallboard da sala de TI (TV) — base entregue 🚧

Possibilidade em avaliação (ainda **não confirmada**): exibir os chamados numa TV
na sala de TI. A direção é um **painel interno somente leitura, com atualização
automática** — e **não** deixar o WhatsApp Web aberto na TV.

**Base entregue:** painel local somente leitura em ``/dashboard`` no servidor
HTTP local (`127.0.0.1`), com a **projeção restrita** do chamado (número,
categoria, prioridade, status, responsável, abertura e tempo em aberto) e
auto-refresh leve. Telefone, texto das mensagens e nome do solicitante ficam
fora da projeção, com teste garantindo. Ver [decisões](decisoes.md), decisões
8 e 12. É um painel de **desenvolvimento**, não de produção.

**Pendente para a TV real:** confirmação do requisito, decisão de
acesso/exposição na rede interna e integração com as Fases 4 (interface de
atendentes) e 5 (observabilidade).

## Atendentes configuráveis ✅

O quadro de atendentes é **rotativo**, então não fica fixado no código.
**Entregue** (ver [decisões](decisoes.md), decisão 11):

- quadro **configurável** em JSON local, apontado por `HELPDESK_ATTENDANTS_PATH`
  (`atendentes.exemplo.json` documenta o formato; o arquivo real é ignorado
  pelo git por poder conter nomes);
- estado **ativo/inativo** — apenas ativos entram no rodízio de novas
  atribuições; inativar alguém não altera chamados já atribuídos;
- **papéis/cargos** livres (ex.: supervisor, efetivo, estagiário, aprendiz,
  suporte), com validação estrita do arquivo (campo desconhecido é erro);
- sem configuração, a demo e os testes usam um quadro de exemplo com papéis
  genéricos.

Mudanças no quadro são aplicadas recarregando o arquivo na inicialização
(reinício do processo); recarga em tempo de execução fica para quando houver a
interface de atendentes (Fase 4). Repositório público: **não** registrar nomes
reais de funcionários nos arquivos — usar papéis genéricos.

## Ajustes incrementais (fora de fase)

Pequenas melhorias de domínio, independentes do plano por fases:

- **Categoria de triagem "empréstimo de equipamento"** (`emprestimo_equipamento`):
  cobre a solicitação de notebook de apoio do setor de TI. Usa gatilhos por frase
  para não conflitar com `hardware`. Detalhes em [decisões](decisoes.md), decisão 6.
- **Modo de demonstração local** (`helpdesk/demo.py` + `demo.ps1`): seed de
  chamados fake pelo fluxo real do serviço e simulação de mensagens via
  `POST /inbound`. Passo a passo em [demo-local](demo-local.md); roteiro de
  apresentação em [roteiro-demo](roteiro-demo.md).
- **Checagem automática da demonstração** (`python -m helpdesk.demo check` /
  `.\demo.ps1 -Check`): percorre o fluxo completo — Python, quadro de
  atendentes, seed, servidor, triagem, follow-up, idempotência e painel — em
  ambiente descartável (banco temporário + porta efêmera) e aponta o passo que
  falhar. Pensada como pré-voo de apresentações.
- **Local/modo de atendimento** (`presencial`/`remoto` + local livre): campos no
  `Ticket`, setter no serviço (`set_attendance`), coluna **Local** no painel e o
  comando `demo locate` para marcar ao vivo. Pela interface dos atendentes fica
  para a Fase 4; o seed já mostra exemplos. Detalhes em
  [decisões](decisoes.md), decisão 18.
- **Esvaziar o banco da demonstração** (`python -m helpdesk.demo clear`): zera
  todos os chamados sem repovoar (decisão 19).
- **Desfecho explícito da mensagem** (`MessageOutcome`: criado/follow-up/
  reaberto): a CLI e o log do servidor passam a relatar o que de fato aconteceu,
  em vez de tratar todo evento como "novo" (decisão 20).

## Decisões em aberto (suas)

Itens que **param o avanço** das fases correspondentes até sua definição.

### 1. Estratégia do número (bloqueia a Fase 3)

O código está pronto para a Cloud API oficial; falta definir **qual número** ela
vai usar. Opções realistas, com trade-offs:

| Opção | Prós | Contras |
|---|---|---|
| **A. Número novo dedicado na Cloud API** (recomendado p/ produção) | Oficial, sem risco de ban; isola o atendimento de números pessoais/da empresa; quem administra é o setor | Precisa de um número/chip novo e do cadastro na conta Business da Meta |
| **B. Migrar o número atual do setor para a Cloud API** | Mantém o número que os funcionários já conhecem | Ao entrar na Cloud API, o número **deixa de funcionar no app comum do WhatsApp** (a migração é definitiva enquanto estiver na API); ninguém mais pode usar aquele número no celular |
| **C. Cliente não-oficial (Baileys/whatsapp-web.js) no número atual** | "Funciona" sem cadastro | **Descartada**: viola os termos do WhatsApp e arrisca **banir** o número (ver [decisões](decisoes.md), decisão 1) |

**Caminho recomendado, que adia o compromisso:** a Cloud API oferece um
**número de teste gratuito** ao criar o app na Meta. Dá para fazer **toda a
validação supervisionada** (roteiro em [pré-integração](pre-integracao.md)) com
esse número de teste — sem comprometer nenhum número real — e só então decidir
entre **A** e **B** para produção.

_Status atual: a decidir. Sem integração real por enquanto._

### 2. Interface dos atendentes (Fase 4)

Painel web (atendente trata o chamado, não só lê) **ou** comandos por WhatsApp.
_Status atual: a decidir._

Ver também: [decisões](decisoes.md) · [pré-integração](pre-integracao.md) ·
[risco de banimento](riscos-banimento.md) · [README](../README.md)
