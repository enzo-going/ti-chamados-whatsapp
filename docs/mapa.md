---
tags: [helpdesk, mapa, documentacao]
---

# Mapa do projeto

Visão de uma tela: as **fases** do roadmap e as **decisões** agrupadas por tema.
Pensado como ponto de partida para navegar a documentação — cada item aponta
para a nota detalhada.

> Nota de cofre (Obsidian): este é um *Map of Content* (MOC). Os diagramas são
> **Mermaid**, que renderiza tanto no Obsidian quanto no GitHub — por isso o
> mapa fica versionado e visível nos dois lugares (ao contrário de um canvas,
> que não vai para o repositório).

## Fases (roadmap)

```mermaid
flowchart LR
    F0["Fase 0 · Fundação<br/>config + logging"]
    F1["Fase 1 · SQLite<br/>persistência"]
    F2["Fase 2 · Entrada<br/>HTTP local + idempotência"]
    F3["Fase 3 · Cloud API<br/>borda pronta · conexão bloqueada"]
    F4["Fase 4 · Atendentes<br/>interface (a decidir)"]
    F5["Fase 5 · Observabilidade<br/>métricas / auditoria"]
    F0 --> F1 --> F2 --> F3 --> F4 --> F5
    classDef done fill:#1f6f43,stroke:#2ea44f,color:#ffffff;
    classDef partial fill:#9a6700,stroke:#d4a72c,color:#ffffff;
    classDef blocked fill:#4b5563,stroke:#9ca3af,color:#ffffff;
    class F0,F1,F2 done
    class F3,F5 partial
    class F4 blocked
```

Legenda: **verde** = feito · **amarelo** = parcial · **cinza** = bloqueado por
decisão sua. O que trava as Fases 3 e 4 são decisões de negócio (estratégia do
número; formato da interface dos atendentes), não código. Critérios completos em
[roadmap](roadmap.md).

## Decisões por tema

Atalho para o [registro de decisões](decisoes.md) (ADR), agrupado por assunto:

| Tema | Decisões |
|---|---|
| Arquitetura & fundação | 1 (projeto próprio), 2 (transporte plugável), 4 (repo em memória) |
| Persistência | 5 (SQLite), 13 (threads + SQLite serializado), 16 (timestamp/reset) |
| Triagem | 3 (palavras-chave), 6 (empréstimo de equipamento) |
| Entrada & resiliência | 7 (idempotência), 9 (follow-up), 15 (best-effort + log), 20 (desfecho/observabilidade) |
| Atendentes | 10 (papéis genéricos), 11 (quadro JSON configurável) |
| Atendimento (local/modo) | 18 (presencial/remoto + local) |
| Painel / wallboard | 8 (direção do wallboard), 12 (painel read-only), 17 (leitura rápida) |
| Integração WhatsApp | 14 (borda Cloud API) · risco em [banimento](riscos-banimento.md) |
| Demonstração | 19 (comando `clear`) |

## Fluxo de uma mensagem (resumo)

```mermaid
flowchart LR
    M["Mensagem recebida"] --> ID{"event_id<br/>já visto?"}
    ID -->|sim| DUP["Reentrega<br/>devolve o mesmo chamado"]
    ID -->|não| O{"Desfecho"}
    O -->|chamado aberto recente| FU["Follow-up<br/>anexa ao chamado"]
    O -->|fechado na janela| RE["Reabertura"]
    O -->|caso geral| NV["Novo chamado<br/>triagem + atribuição"]
```

Detalhe (diagramas de sequência e ciclo de vida) em [arquitetura](arquitetura.md);
o desfecho explícito é a decisão 20.

## Atalhos

- [Arquitetura](arquitetura.md) — componentes, fluxo e ciclo de vida (diagramas).
- [Roadmap](roadmap.md) — fases e decisões em aberto.
- [Registro de decisões](decisoes.md) — ADR completo.
- [Risco de banimento no WhatsApp](riscos-banimento.md) — por que o uso é de baixo risco.
- [Checklist de pré-integração](pre-integracao.md) — antes de conectar uma linha real.
- [Demonstração local](demo-local.md) · [Roteiro de demonstração](roteiro-demo.md)
- [Índice](index.md) — lista de documentos + mapa do código.
