---
tags: [helpdesk, integracao, checklist]
---

# Checklist de pré-integração (linha de WhatsApp)

Checklist técnico do que precisa estar verde **antes** de conectar uma linha
real de mensagens (Fase 3 do [roadmap](roadmap.md)). Nada aqui conecta serviço
externo: o objetivo é validar, só com recursos locais, que o núcleo está pronto
para receber a borda real quando a decisão for tomada.

> ⚠️ A Fase 3 continua **bloqueada por decisão** (estratégia do número — ver
> [decisões](decisoes.md)). Este checklist não autoriza nem executa integração
> real; ele apenas elimina pendências locais para o dia em que ela for liberada.

## O que o núcleo já garante (sem tocar em produção)

- **Transporte plugável:** o serviço fala com a interface `MessagingTransport`;
  a demo e os testes usam o `FakeTransport`. A integração real entra como uma
  implementação nova, sem mexer no domínio.
- **Entrada neutra com idempotência:** `POST /inbound` recebe payload JSON
  neutro com `event_id`; reentregas não duplicam chamados (persistido em
  `processed_events`).
- **Follow-up:** mensagem seguida do mesmo remetente cai no chamado aberto.
- **Privacidade no painel:** `/dashboard` recebe apenas a projeção restrita
  (sem telefone, nome do solicitante ou texto das mensagens), com teste
  garantindo.
- **Servidor local:** o HTTP escuta somente em `127.0.0.1`, sem exposição.

## Checklist pré-voo

Rode na máquina que fará a validação, na raiz do repositório:

1. **Suíte de testes verde:**
   `python -m unittest discover -s tests`
2. **Configuração local ok (sem segredos na tela):**
   `python -m helpdesk.config check`
   — valida caminho do banco, quadro de atendentes e reporta as variáveis
   reservadas apenas como definida/não definida.
3. **Fluxo completo ok em ambiente descartável:**
   `python -m helpdesk.demo check`
   — seed, servidor efêmero, triagem, follow-up, idempotência e painel.
4. **Quadro de atendentes real preparado:** copiar
   `atendentes.exemplo.json` → `atendentes.json` (não versionado), preencher e
   apontar `HELPDESK_ATTENDANTS_PATH`. Sem nomes reais em arquivos versionados.
5. **Variáveis de ambiente da integração definidas no ambiente local**
   (nomes em [`.env.example`](../.env.example); valores nunca entram no
   repositório). O item 2 confirma a presença sem exibir valores.
6. **Decisão da estratégia do número registrada** em
   [decisões](decisoes.md) — é o que desbloqueia a Fase 3.
7. **Varredura de segredos/termos indevidos** no diff antes de qualquer
   commit (repositório público).

## O que continua fora do repositório

- `.env`, tokens e qualquer credencial (somente nomes em `.env.example`);
- `atendentes.json` (pode conter nomes) e bancos locais `*.sqlite3` — ambos já
  ignorados pelo git;
- números de telefone reais, nomes reais e mensagens reais — dados de
  demonstração são sempre fictícios.

## Fora do escopo deste checklist

- Implementar o transporte real (envio + verificação/assinatura do webhook):
  isso **é** a Fase 3, que permanece bloqueada até a decisão do número.
- Expor o servidor para fora de `127.0.0.1` ou colocar webhook público.

Ver também: [roadmap](roadmap.md) · [demo local](demo-local.md) ·
[índice da documentação](index.md)
