# ti-chamados-whatsapp

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-unittest-brightgreen?style=flat)
![Dependencies](https://img.shields.io/badge/Dependencies-none-brightgreen?style=flat)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat)

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

**Demonstração completa em um comando** (Windows/PowerShell): `.\demo.ps1` —
cria um banco com chamados fake, sobe o servidor local e abre o painel no
navegador. Passo a passo manual, simulação de mensagens e solução de problemas
em [`docs/demo-local.md`](docs/demo-local.md).

**Aplicativo Windows:** a versão empacotada abre por um atalho na Área de
Trabalho, inicia o servidor local em uma porta livre, abre o painel e oferece
uma caixa para simular mensagens. O banco persiste em
`%LOCALAPPDATA%\TIChamadosWhatsApp`; fechar a janela encerra o servidor. Ela
continua sendo uma demonstração local, sem conexão com WhatsApp real.

```bash
# Diagnóstico seguro da configuração local (não exibe valores de variáveis)
python -m helpdesk.config check

# Pré-voo da demonstração: percorre o fluxo completo em ambiente descartável
python -m helpdesk.demo check

# Banco de demonstração com chamados fake (recriável à vontade)
python -m helpdesk.demo seed --reset

# Esvaziar o banco da demonstração (apaga todos os chamados, sem repovoar)
python -m helpdesk.demo clear

# Simular uma mensagem chegando (com o servidor local rodando)
python -m helpdesk.demo send "a impressora do RH parou"

# Marcar o local/modo de atendimento de um chamado (presencial/remoto)
python -m helpdesk.demo locate 6 --modo presencial --local "Sala 203"

# Demonstração com um roteiro de mensagens de exemplo
python main.py

# Modo interativo: você digita as mensagens
python main.py --repl

# Persistindo os chamados em SQLite (sobrevive a reinícios)
python main.py --db chamados.sqlite3

# Camada de entrada via HTTP local (127.0.0.1; recebe eventos em JSON)
# e painel somente leitura em http://127.0.0.1:8000/dashboard
python -m helpdesk.http_app --db chamados.sqlite3

# Quadro de atendentes configurável (papéis + ativo/inativo, sem hardcode)
cp atendentes.exemplo.json atendentes.json    # edite à vontade; não é versionado
HELPDESK_ATTENDANTS_PATH=atendentes.json python main.py

# Testes
python -m unittest discover -s tests
```

### Gerar e instalar o aplicativo Windows

O núcleo continua sem dependências de runtime. O script cria um ambiente de
build isolado, instala nele o empacotador e gera o `.exe`:

```powershell
.\build_windows.ps1 -Install
```

O build cria `dist\TI Chamados WhatsApp.exe`, executa uma checagem silenciosa do
pacote e só então instala. A instalação copia o executável para
`%LOCALAPPDATA%\Programs\TI Chamados WhatsApp` e cria o atalho
`TI Chamados WhatsApp` na Área de Trabalho, com o ícone próprio do projeto.

Exemplo de saída do `python main.py`:

```
[5513990000001] Bom dia! A rede caiu aqui no segundo andar, ninguém consegue acessar nada
  -> Chamado #1 | rede | prioridade alta | atendente: Atendente 1 (supervisor)
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
├── attendants.py  # quadro de atendentes configurável (JSON local: papéis, ativo/inativo)
├── repository.py  # armazenamento: em memória (demo/testes) + SQLite (persistente)
├── config.py      # caminhos via env: HELPDESK_DB_PATH, HELPDESK_ATTENDANTS_PATH
├── transport.py   # interface de envio + FakeTransport para testes
├── replies.py     # mensagens automáticas (pt-BR)
├── inbound.py     # payload neutro → Message, com idempotência por event_id
├── whatsapp.py    # borda da Cloud API: webhook (verificação + assinatura) e envio (HTTP injetável)
├── http_app.py    # servidor HTTP local (127.0.0.1): entrada + painel + /webhook
├── dashboard.py   # painel somente leitura (projeção restrita; base do wallboard)
├── demo.py        # demonstração: seed fake, simulação de mensagens e checagem (check)
├── desktop.py     # controlador gráfico e ciclo de vida do servidor local no Windows
└── service.py     # orquestra o fluxo completo
tests/             # suíte de testes (unittest)
main.py            # demonstração CLI com transporte de mentira
demo.ps1           # demo completa em um comando (Windows)
desktop_app.py     # entrada usada para gerar o aplicativo Windows
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
| empréstimo de equipamento | "preciso de um notebook", "notebook emprestado", "reserva de notebook", "notebook para reunião", "equipamento temporário" |
| `outros` | fallback |

Prioridade **alta** é inferida por sinais de impacto coletivo ("caiu", "ninguém
consegue", "urgente"); **baixa** por sinais de dúvida sem pressa. O casamento é
por palavra inteira (ex.: "rede**finir**" não é classificado como rede).

> A triagem foi deixada isolada de propósito: pode ser trocada por um
> classificador de ML/NLP no futuro sem mexer no resto.

---

## Atendentes

A equipe de atendimento é rotativa, então o quadro **não é fixado no código**:
é um arquivo JSON local apontado por `HELPDESK_ATTENDANTS_PATH`, com `id`,
`name`, `role` (papel/cargo livre — ex.: supervisor, efetivo, estagiário) e
`active`. Apenas atendentes **ativos** entram no rodízio de novas atribuições;
inativar alguém não altera os chamados já atribuídos a essa pessoa. Sem
configuração, a demo usa um quadro de exemplo com papéis genéricos —
[`atendentes.exemplo.json`](atendentes.exemplo.json) mostra o formato. O arquivo
real (`atendentes.json`) fica fora do versionamento por poder conter nomes.

---

## Painel local somente leitura (wallboard)

O servidor HTTP local serve em `/dashboard` uma página HTML simples com os
chamados em aberto — pensada como base para um futuro **wallboard** (TV na sala
de TI). A página recebe apenas uma **projeção restrita** do chamado: número,
categoria, prioridade, status, responsável, local/modo de atendimento, horário
de abertura e tempo em aberto. Telefone, nome do solicitante e conteúdo das
mensagens **não passam pela projeção** (há teste garantindo isso). Ordena por prioridade (alta
primeiro) e idade, com auto-refresh leve via `<meta refresh>`.

> É um painel **local de desenvolvimento** (`127.0.0.1`, sem autenticação),
> não uma interface de produção.

---

## Próximos passos (planejados)

- [x] **Borda da Cloud API testável sem rede** (`helpdesk/whatsapp.py`):
      verificação do webhook, assinatura HMAC, parser do payload e transporte
      de envio com HTTP injetável — roteiro de validação em
      [`docs/pre-integracao.md`](docs/pre-integracao.md)
- [ ] **Conexão real** com a Cloud API (número de teste → produção; depende da
      decisão da estratégia do número)
- [x] Persistência em **SQLite** (Fase 1 concluída; SQLAlchemy fica como opção futura)
- [x] **Atendentes configuráveis** (JSON local com papéis e ativo/inativo, sem hardcode)
- [x] **Painel local somente leitura** (`/dashboard`; projeção restrita, base do wallboard)
- [ ] Painel web para os atendentes verem e **tratarem** os chamados
- [ ] Métricas: tempo de resposta, chamados por categoria, carga por atendente
- [ ] Notificação aos atendentes quando um chamado de prioridade alta entra

---

## Decisões de projeto

Ver [`docs/decisoes.md`](docs/decisoes.md) para o registro de decisões
(por que projeto próprio em vez de fork, por que transporte plugável, etc.) e
[`docs/roadmap.md`](docs/roadmap.md) para o plano incremental por fases.

---

## Licença

Distribuído sob a licença MIT — ver [`LICENSE`](LICENSE).
