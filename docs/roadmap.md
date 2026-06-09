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
| 2 | Entrada HTTP (webhook) + idempotência + follow-up de chamado aberto | 🔜 próxima |
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

## Fase 2 — Entrada HTTP (webhook) 🔜

Próxima fase candidata. Um ponto de entrada HTTP que recebe payloads, um
**adaptador** que converte payload → `Message`, **idempotência** por id de
mensagem (evita chamados duplicados em reentregas) e correção do gap em que uma
nova mensagem de um chamado **aberto** abre um chamado novo em vez de anexar.
Continua **testável sem WhatsApp real** (payloads de exemplo).

## Fases 3–5 — resumo

- **3. WhatsApp Cloud API:** transporte de envio real + verificação/assinatura do
  webhook. **Bloqueada** até decidir a estratégia do número (ver abaixo).
- **4. Atendentes:** painel web mínimo *ou* comandos por WhatsApp. Depende da sua
  escolha.
- **5. Observabilidade:** métricas, notificação de prioridade alta, logs de
  auditoria.

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
