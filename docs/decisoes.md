# Registro de decisões

Documento curto explicando as escolhas principais do projeto.

## 1. Projeto próprio em Python em vez de adaptar o fork do WhaTicket

**Contexto:** existe um fork de `whaticket-community` (Node.js/TypeScript + React +
MySQL) que resolve um problema parecido (WhatsApp → tickets, multi-atendente).

**Decisão:** construir um projeto próprio em Python.

**Por quê:**
- **Peso de portfólio.** Um fork aparece como "forked from..." e mostra pouco
  trabalho autoral. Um projeto próprio demonstra design e decisões minhas.
- **Stack.** Meu portfólio é majoritariamente Python; o WhaTicket é TS/JS/React.
  Manter coerência com o resto do perfil é mais forte do que carregar uma stack
  que não é a minha.
- **Escopo.** O WhaTicket é uma plataforma grande (755+ commits). Para o caso do
  setor de TI (helpdesk interno) eu não preciso de tudo aquilo — um núcleo enxuto
  e bem testado atende melhor e é viável de manter sozinho.
- **Risco de ToS.** O WhaTicket usa `whatsapp-web.js` (cliente não-oficial), que
  pode resultar em bloqueio da conta. Projetando com transporte plugável, posso
  usar a **Cloud API oficial** quando for integrar.

**O WhaTicket continua útil** como referência conceitual (ex.: a regra de reabrir
o último chamado quando a mesma pessoa escreve em seguida veio de lá).

## 2. Transporte de mensagens como interface plugável

O serviço depende de `MessagingTransport`, não de uma biblioteca de WhatsApp.
Em testes/demonstração uso `FakeTransport`. Isso mantém a regra de negócio 100%
testável e adia a integração real (que envolve credenciais e produção) sem
travar o desenvolvimento.

## 3. Triagem por palavras-chave (por enquanto)

Comecei com classificação por palavras-chave porque é transparente, rápida e sem
dependências — fácil de revisar e de explicar. A função está isolada em
`triage.py` para poder ser trocada por um modelo de ML/NLP depois sem afetar o
resto do sistema.

## 4. Repositório em memória primeiro

A persistência é uma interface (`TicketRepository`) com uma implementação em
memória. Quando fizer sentido, entra SQLite/SQLAlchemy (stack que já uso em
outros projetos) sem alterar o serviço.

> Concretizado na **Fase 1** — ver decisão 5 e o [roadmap](roadmap.md).

## 5. Persistência SQLite (Fase 1 — implementada em 2026-06-08)

A interface já previa SQLite (decisão 4); a Fase 1 a tornou real com
`SqliteTicketRepository`, **sem alterar a regra de negócio** — o serviço continua
falando apenas com o `Protocol`. Escolhas:

- **`sqlite3` da biblioteca padrão, não SQLAlchemy.** O modelo é praticamente uma
  entidade (`Ticket`); um ORM seria peso sem ganho agora. Mantém o projeto sem
  dependências de runtime. A interface continua permitindo migrar para SQLAlchemy
  depois, se a complexidade crescer.
- **Write-back explícito (`update()`).** O repositório em memória "enxergava" as
  mutações do `Ticket` por compartilhar a referência do objeto; uma persistência
  real não. Por isso o contrato ganhou `update()` e o serviço passou a chamá-lo
  após cada mutação (atribuição, reabertura, início, resolução, fechamento). Isso
  completa o padrão Repository sem acoplar o domínio ao banco.
- **`next_id()` via `MAX(id) + 1`.** Mantém o contrato (id conhecido antes do
  insert) e é naturalmente persistente: IDs não colidem após reinício. Como
  chamados nunca são apagados, não há risco de reuso de id.
- **Datas em ISO 8601 (UTC); histórico em JSON.** Para timestamps UTC a ordem
  lexicográfica coincide com a cronológica, então a busca pelo último chamado
  fechado usa `ORDER BY closed_at` diretamente.

**Deferido de propósito (não é dívida esquecida):** o estado do rodízio
(`round-robin`) continua em memória. Persisti-lo exigiria mover estado do
*serviço* para o *repositório* — uma decisão de design que prefiro discutir antes
de tomar. O efeito de não persistir é apenas cosmético (após um restart a
distribuição entre atendentes pode recomeçar do primeiro); não há perda de dados.
Registrado no [roadmap](roadmap.md).

## 6. Categoria de triagem para empréstimo de equipamento

Adicionada a categoria `emprestimo_equipamento` (nome público: **empréstimo de
equipamento**) para solicitações de notebook de apoio do setor de TI.

**Ambiguidade tratada:** "notebook" já era gatilho de `hardware` (equipamento com
defeito). Para distinguir *solicitar* de *defeito*, a categoria usa **gatilhos por
frase** ("preciso de um notebook", "notebook emprestado", "reserva de notebook",
"notebook para reunião", "equipamento temporário"…) e fica **antes de `hardware`**
na ordem de classificação. Assim, frases de solicitação vencem, enquanto
"meu notebook não liga" continua em `hardware`. Há teste de regressão garantindo
esse comportamento, além de um teste que verifica que toda categoria tem rótulo
público em `replies.py`.

---

## Em aberto (a confirmar com o contexto do setor de TI)

- Quais categorias fazem mais sentido no dia a dia do CAMPS?
- A equipe tem 4 atendentes fixos? O rodízio simples basta ou precisa considerar
  quem está disponível?
- Faz sentido notificar os atendentes (ex.: por outro canal) quando entra um
  chamado de prioridade alta?
- Qual o tom desejado nas mensagens automáticas?
