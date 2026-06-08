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

---

## Em aberto (a confirmar com o contexto do setor de TI)

- Quais categorias fazem mais sentido no dia a dia do CAMPS?
- A equipe tem 4 atendentes fixos? O rodízio simples basta ou precisa considerar
  quem está disponível?
- Faz sentido notificar os atendentes (ex.: por outro canal) quando entra um
  chamado de prioridade alta?
- Qual o tom desejado nas mensagens automáticas?
