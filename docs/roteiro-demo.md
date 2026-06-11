---
tags: [helpdesk, demo, apresentacao]
---

# Roteiro de demonstração (≈10 minutos)

Guia curto para apresentar o sistema a alguém de fora do desenvolvimento
(ex.: liderança do setor de TI). Pré-requisitos: ter rodado a
[demonstração local](demo-local.md) ao menos uma vez antes e, minutos antes de
começar, rodar `python -m helpdesk.demo check` — 8 passos verdes significam
zero surpresa ao vivo.

## 1. O problema (1 min)

> "Hoje os pedidos chegam num WhatsApp compartilhado do setor. Sem organização,
> não dá para saber o que foi pedido, quem está atendendo, o que é urgente e o
> que já foi resolvido."

## 2. O que o sistema faz (1 min)

> "Cada mensagem vira um **chamado**: o sistema classifica o assunto e a
> prioridade automaticamente, distribui entre os atendentes em rodízio e
> responde ao funcionário na hora. Mensagens repetidas não viram chamados
> duplicados."

Ressalva importante (transparência): a integração com o WhatsApp de verdade
ainda **não** está ligada — a entrada é uma interface pronta para receber
qualquer plataforma. Toda a demonstração roda local, com dados fictícios.

## 3. Demo ao vivo (5 min)

Antes: `.\demo.ps1` (painel abre sozinho no navegador).

1. **Painel na tela.** Mostrar as colunas: número, categoria, prioridade,
   status, responsável, tempo aberto. Apontar: alta prioridade no topo,
   destacada; o resumo de contagem; o auto-refresh.
   > "É isto que ficaria numa TV da sala: visão imediata do que está pendente
   > e com quem está — sem expor telefone nem o conteúdo das conversas."
2. **Mensagem chegando.** Em outra janela:
   ```powershell
   python -m helpdesk.demo send "a impressora do RH parou de novo"
   ```
   Recarregar o painel: chamado novo, categoria "Impressora", responsável
   atribuído automaticamente.
3. **Pessoa insiste (follow-up).**
   ```powershell
   python -m helpdesk.demo send "continua sem imprimir nada"
   ```
   Mostrar que **não** abriu chamado novo — a mensagem foi anexada ao mesmo
   chamado. "O sistema entende que é o mesmo assunto."
4. **Reentrega técnica (idempotência).** Enviar duas vezes com o mesmo
   `--event-id`:
   ```powershell
   python -m helpdesk.demo send "teste" --sender 5513990000043 --event-id evt-1
   python -m helpdesk.demo send "teste" --sender 5513990000043 --event-id evt-1
   ```
   "Mesmo se a plataforma entregar o evento duas vezes, nada duplica."

## 4. Como foi construído (1 min)

> "A regra de negócio é independente do WhatsApp: hoje os testes e a demo usam
> um transporte simulado, e a integração oficial entra depois sem reescrever
> nada. São 121 testes automatizados, sem dependências externas — Python puro
> e SQLite."

## 5. Próximos passos possíveis (1 min)

- Integração oficial (WhatsApp Cloud API) — depende da decisão sobre o número.
- Interface para os atendentes tratarem chamados (painel web ou comandos).
- Wallboard definitivo na TV da sala (o painel atual é a base).
- Métricas: tempo de resposta, volume por categoria, carga por atendente.

## Perguntas prováveis

| Pergunta | Resposta curta |
|---|---|
| "Já está ligado no WhatsApp?" | Não — por decisão. A borda é plugável; ligar exige definir o número/conta oficial. |
| "Os dados são reais?" | Não, tudo fictício. O painel, por construção, nunca mostra telefone nem conversa. |
| "E se dois mandarem ao mesmo tempo?" | Cada mensagem vira evento com id único; chamados não se misturam entre remetentes. |
| "Quem atende o quê?" | Rodízio automático entre os atendentes **ativos** — o quadro é configurável, sem mexer em código. |
| "Roda onde?" | Qualquer máquina com Python; hoje é local. Exposição na rede interna é etapa futura, junto com acesso controlado. |
