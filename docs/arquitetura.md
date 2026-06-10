---
tags: [helpdesk, arquitetura]
---

# Arquitetura

Visão técnica de como o sistema está organizado. Resumo: **a regra de negócio
fica isolada no centro e só conversa com interfaces (portas); as integrações
externas entram como adaptadores nas bordas.** É o estilo *ports & adapters*
(hexagonal), escolhido para manter o domínio testável sem WhatsApp real e para
trocar as bordas (mensageria, persistência) sem reescrever a lógica.

## Mapa de componentes

```mermaid
flowchart TB
    subgraph Bordas["Adaptadores (bordas)"]
        IN["Entrada de mensagens<br/>(demo CLI · HTTP local)"]
        FAKE["FakeTransport"]
        MEM["InMemoryTicketRepository"]
        SQL["SqliteTicketRepository"]
    end

    subgraph Nucleo["Núcleo de domínio (sem I/O)"]
        SVC["HelpdeskService<br/>(orquestra o fluxo)"]
        TRI["triage<br/>(categoria + prioridade)"]
        REP["replies<br/>(mensagens pt-BR)"]
        MOD["models<br/>(Ticket, Message, enums)"]
    end

    IN -->|Message| SVC
    SVC --> TRI
    SVC --> REP
    SVC --> MOD
    SVC -->|porta: MessagingTransport| FAKE
    SVC -->|porta: TicketRepository| MEM
    SVC -->|porta: TicketRepository| SQL
```

O núcleo depende apenas dos `Protocol` `MessagingTransport` e `TicketRepository`
(as portas). Os adaptadores concretos são plugados de fora, na composição
(`main.py` e os testes).

## Fluxo de uma mensagem recebida

```mermaid
sequenceDiagram
    participant F as Funcionário
    participant S as HelpdeskService
    participant T as Triagem
    participant R as TicketRepository
    participant M as MessagingTransport

    F->>S: handle_message(Message)
    S->>R: last_closed_for(remetente)
    alt Chamado fechado dentro da janela de reabertura
        S->>R: update(chamado, status = ABERTO)
        S->>M: send(resposta de reabertura)
    else Caso geral (novo chamado)
        S->>T: classifica categoria, prioridade e assunto
        S->>R: next_id() + add(novo chamado)
        S->>S: atribui atendente (rodízio)
        S->>R: update(chamado, status = ATRIBUIDO)
        S->>M: send(confirmação de abertura)
    end
    S-->>F: Ticket
```

## Ciclo de vida do chamado

```mermaid
stateDiagram-v2
    [*] --> ABERTO
    ABERTO --> ATRIBUIDO: atribuição (rodízio)
    ATRIBUIDO --> EM_ANDAMENTO: start_progress()
    EM_ANDAMENTO --> RESOLVIDO: resolve()
    RESOLVIDO --> FECHADO: close()
    RESOLVIDO --> ABERTO: nova mensagem dentro da janela
    FECHADO --> ABERTO: nova mensagem dentro da janela
```

`resolve()` e `close()` registram `closed_at`; é esse instante que a janela de
reabertura compara com a chegada de uma nova mensagem do mesmo remetente.

## Responsabilidades por módulo

| Camada | Módulo | Responsabilidade |
|---|---|---|
| Domínio | `helpdesk/models.py` | Entidades e enums; objetos puros, sem I/O |
| Domínio | `helpdesk/triage.py` | Classifica texto em categoria/prioridade e gera o assunto |
| Domínio | `helpdesk/replies.py` | Monta as mensagens automáticas (pt-BR) |
| Orquestração | `helpdesk/service.py` | Follow-up, reabertura, criação, atribuição e resposta |
| Porta | `helpdesk/transport.py` | `MessagingTransport` + `FakeTransport` |
| Porta | `helpdesk/repository.py` | `TicketRepository` + implementações memória/SQLite |
| Borda | `helpdesk/inbound.py` | Payload neutro → `Message`, com idempotência por `event_id` |
| Borda | `helpdesk/http_app.py` | Servidor HTTP local (`127.0.0.1`) da camada de entrada |
| Configuração | `helpdesk/config.py` | Caminhos (banco, quadro de atendentes) via variáveis de ambiente |
| Configuração | `helpdesk/attendants.py` | Carrega e valida o quadro de atendentes (JSON local) |
| Composição | `main.py` | Liga adaptadores ao núcleo (demo CLI) |

## Pontos de extensão

Cada borda foi pensada para crescer sem tocar no núcleo:

- **Mensageria:** uma nova implementação de `MessagingTransport` cobre o envio
  real, sem mudar o `HelpdeskService`.
- **Persistência:** `InMemoryTicketRepository` (testes/demo) e
  `SqliteTicketRepository` (persistente) compartilham o mesmo contrato; outras
  implementações entram da mesma forma.
- **Triagem:** hoje por palavras-chave, isolada em `triage.py`. Pode ser trocada
  por outro classificador sem afetar o restante.
- **Entrada:** a demo injeta `Message` diretamente; uma camada de entrada futura
  produzirá `Message` a partir de outra fonte, mantendo o mesmo ponto de contato.

## Por que assim

Separar regra de negócio de integração é o que permite **testar tudo de ponta a
ponta sem dependências externas** e adiar decisões de borda (que envolvem
credenciais e produção) sem travar o desenvolvimento. As decisões que levaram a
este desenho estão registradas em [decisões](decisoes.md); o plano por fases
está no [roadmap](roadmap.md).
