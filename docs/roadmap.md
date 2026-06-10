# Roadmap — protótipo → MVP

Documento vivo do plano incremental para transformar o protótipo em um MVP real
de helpdesk de TI por WhatsApp. Atualizado a cada fase.

## Legenda de status

- ✅ concluído  ·  🔜 próximo  ·  ⏳ planejado  ·  ⛔ bloqueado por decisão sua

## Visão geral das fases

| Fase | Objetivo | Status |
|---|---|---|
| 0 | Fundação: config via env + logging | ⏳ (config já entrou na Fase 1) |
| **1** | **Persistência SQLite** | **✅ concluída em 2026-06-08** |
| 2 | Entrada HTTP local + idempotência + follow-up de chamado aberto | 🚧 em andamento |
| 3 | Integração WhatsApp Cloud API (envio + segurança do webhook) | ⛔ depende da decisão do número |
| 4 | Interface para atendentes (painel web ou comandos) | ⛔ depende da sua escolha |
| 5 | Observabilidade: métricas, notificação de prioridade alta, auditoria | ⏳ |

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
python -m unittest discover -s tests        # 38 testes
python main.py --db chamados.sqlite3         # roda; rode 2x: os IDs continuam
```

**Deferido (decisão consciente):** persistência do estado de rodízio
(`round-robin`) — ver [decisões](decisoes.md).

## Fase 2 — Entrada HTTP local + idempotência 🚧

**Entregue (inicial, tudo local e sem integração externa):**

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

**Pendente nesta frente:** o transporte/borda reais de entrada e saída, que
dependem das decisões da Fase 3 (estratégia do número).

**Fora de escopo (continua valendo):** sem WhatsApp real, sem Cloud API, sem
webhook público exposto, sem credenciais.

## Fases 3–5 — resumo

- **3. WhatsApp Cloud API:** transporte de envio real + verificação/assinatura do
  webhook. **Bloqueada** até decidir a estratégia do número (ver abaixo).
- **4. Atendentes:** painel web mínimo *ou* comandos por WhatsApp. Depende da sua
  escolha.
- **5. Observabilidade:** métricas, notificação de prioridade alta, logs de
  auditoria.

## Requisito futuro — Wallboard da sala de TI (TV)

Possibilidade em avaliação (ainda **não confirmada**): exibir os chamados numa TV
na sala de TI. A direção pretendida é um **painel interno somente leitura, com
atualização automática** — e **não** deixar o WhatsApp Web aberto na TV.

O painel deve mostrar apenas dados **operacionais**: número do chamado, categoria,
prioridade, status, responsável e tempo em aberto. Deve **omitir** telefone,
texto completo das mensagens, nomes desnecessários e qualquer dado sensível —
ou seja, uma **projeção restrita** do chamado (subconjunto seguro de campos).

Tende a se apoiar na interface de atendentes (Fase 4) e/ou na observabilidade
(Fase 5); um wallboard é uma visão somente leitura sobre os chamados abertos.
Sem implementação por enquanto — apenas registro. Consideração de privacidade em
[decisões](decisoes.md), decisão 8.

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

## Decisões em aberto (suas)

Itens que **param o avanço** das fases correspondentes até sua definição:

1. **Número do WhatsApp** (bloqueia Fase 3): número novo dedicado na Cloud API,
   cliente não-oficial no número atual (risco de ban / ToS), ou decidir depois.
   _Status atual: decidir depois — sem integração real por enquanto._
2. **Interface dos atendentes** (Fase 4): painel web ou comandos por WhatsApp.
   _Status atual: decidir depois._

Ver também: [decisões](decisoes.md) · [README](../README.md)
