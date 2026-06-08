# ti-chamados-whatsapp

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-unittest-brightgreen?style=flat)
![Dependencies](https://img.shields.io/badge/Dependencies-none-brightgreen?style=flat)

Núcleo de um **helpdesk de TI** que transforma mensagens de WhatsApp em chamados
organizados — pensado para o cenário de um setor de TI que atende funcionários
por um WhatsApp compartilhado (vários atendentes, uma conta).

> ⚠️ **Status: protótipo / portfólio.** A integração real com o WhatsApp ainda
> **não** está conectada — o transporte de mensagens é uma interface plugável.
> Todo o comportamento é demonstrável e testável sem tocar em produção.

---

## O problema

No setor de TI, funcionários mandam mensagens para um WhatsApp compartilhado
("a rede caiu aqui", "a impressora parou", "esqueci minha senha"). Sem
organização, é difícil saber **o que** foi pedido, **quem** está atendendo e
**qual** a prioridade. Este projeto estrutura esse fluxo:

1. Mensagem chega → **triagem automática** (categoria + prioridade)
2. Abre um **chamado** com assunto e histórico
3. **Atribui** a um atendente (rodízio entre a equipe)
4. Envia uma **confirmação automática** ao funcionário
5. Mensagens repetidas da mesma pessoa logo em seguida **reabrem** o chamado
   recente em vez de duplicar

---

## Como rodar

Sem dependências externas — Python 3.10+ puro.

```bash
# Demonstração com um roteiro de mensagens de exemplo
python main.py

# Modo interativo: você digita as mensagens
python main.py --repl

# Testes
python -m unittest discover -s tests
```

Exemplo de saída do `python main.py`:

```
[5513990000001] Bom dia! A rede caiu aqui no segundo andar, ninguém consegue acessar nada
  -> Chamado #1 | rede | prioridade alta | atendente: Enzo
    resposta automática: ✅ Recebemos seu chamado *#1*.
```

---

## Arquitetura

A lógica de domínio é **agnóstica de WhatsApp**. O serviço conversa apenas com
interfaces (`MessagingTransport`, `TicketRepository`), então dá para testar tudo
de ponta a ponta e trocar as bordas depois.

```
helpdesk/
├── models.py      # Ticket, Message, Attendant, enums (Category/Priority/Status)
├── triage.py      # classificação por palavras-chave (categoria + prioridade)
├── repository.py  # armazenamento (em memória; SQLite/SQLAlchemy depois)
├── transport.py   # interface de envio + FakeTransport para testes
├── replies.py     # mensagens automáticas (pt-BR)
└── service.py     # orquestra o fluxo completo
tests/             # 26 testes (unittest)
main.py            # demonstração CLI com transporte de mentira
```

**Por que assim:** separar a regra de negócio das integrações é o que permite
testar sem WhatsApp real e plugar o transporte oficial depois sem reescrever nada.

---

## Triagem

| Categoria | Exemplos de gatilho |
|---|---|
| `rede` | "rede caiu", "sem internet", "wifi" |
| `hardware` | "computador não liga", "monitor", "teclado" |
| `software` | "sistema travou", "programa", "lento" |
| `acesso` | "senha", "login", "email bloqueado" |
| `impressora` | "impressora", "imprimir", "toner" |
| `outros` | fallback |

Prioridade **alta** é inferida por sinais de impacto coletivo ("caiu", "ninguém
consegue", "urgente"); **baixa** por sinais de dúvida sem pressa. O casamento é
por palavra inteira (ex.: "rede**finir**" não é classificado como rede).

> A triagem foi deixada isolada de propósito: pode ser trocada por um
> classificador de ML/NLP no futuro sem mexer no resto.

---

## Próximos passos (planejados)

- [ ] Adaptador de transporte com a **WhatsApp Cloud API** (oficial, sem risco de ban)
- [ ] Persistência em **SQLite/SQLAlchemy** (a interface já está pronta)
- [ ] Painel web (Flask) para os atendentes verem e tratarem os chamados
- [ ] Métricas: tempo de resposta, chamados por categoria, carga por atendente
- [ ] Notificação aos atendentes quando um chamado de prioridade alta entra

---

## Decisões de projeto

Ver [`docs/decisoes.md`](docs/decisoes.md) para o registro de decisões
(por que projeto próprio em vez de fork, por que transporte plugável, etc.).
