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

## Borda da Cloud API já implementada (local, sem conexão)

`helpdesk/whatsapp.py` entrega as peças que a integração exige, todas
testadas sem rede (`tests/test_whatsapp.py`):

- **Handshake de verificação do webhook** (`GET /webhook` com `hub.mode`,
  `hub.verify_token`, `hub.challenge`) — comparação de token em tempo
  constante.
- **Validação de assinatura** `X-Hub-Signature-256` (HMAC-SHA256 do corpo
  bruto com o app secret) — sem assinatura válida, o evento é recusado (403);
  sem configuração, as rotas respondem 503 (fail closed).
- **Parser do payload de webhook** → payloads neutros do `/inbound`: o id da
  mensagem vira `event_id`, ligando reentregas da plataforma à idempotência
  já persistida. Recibos de status e tipos não suportados são ignorados com
  motivo (sem conteúdo de mensagem nos motivos).
- **`CloudApiTransport`** (envio): monta a chamada da Graph API com a função
  HTTP **injetável** — em teste, nenhuma requisição externa; o token nunca
  aparece em `repr`/erros. Ativado por `--transport cloud-api` no
  `helpdesk.http_app`, que exige as variáveis de ambiente e falha citando só
  os nomes.

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

## Roteiro do dia da validação (quando a Fase 3 for liberada)

Passos operacionais para o teste supervisionado com **número de teste** — em
ordem; nenhum deles entra no repositório:

1. Criar o app na plataforma da API oficial e anotar (fora do repo): token de
   acesso, id do número de teste, app secret; escolher um verify token.
2. Definir as quatro variáveis no ambiente do terminal
   (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`,
   `WHATSAPP_APP_SECRET`) e conferir com `python -m helpdesk.config check`.
3. Subir o servidor local: `python -m helpdesk.http_app --db teste.sqlite3
   --transport cloud-api` (o resumo de inicialização mostra as rotas
   `/webhook` ativas, sem exibir valores).
4. Expor `127.0.0.1:8000` por um túnel HTTPS temporário (o servidor continua
   ligado só em loopback; o túnel é a única porta de entrada e morre com o
   teste).
5. Registrar a URL do túnel + `/webhook` na plataforma; o handshake GET deve
   passar na primeira tentativa.
6. Enviar uma mensagem do número de teste e acompanhar: chamado criado,
   resposta automática recebida, painel atualizado, reentrega sem duplicar.
7. Ao final: derrubar o túnel, revogar/rotacionar o token de teste e limpar as
   variáveis do ambiente.

## O que continua fora do repositório

- `.env`, tokens e qualquer credencial (somente nomes em `.env.example`);
- `atendentes.json` (pode conter nomes) e bancos locais `*.sqlite3` — ambos já
  ignorados pelo git;
- números de telefone reais, nomes reais e mensagens reais — dados de
  demonstração são sempre fictícios.

## Fora do escopo deste checklist

- **Conectar de fato** (registrar webhook público e usar token real): depende
  da decisão da estratégia do número e de acompanhamento supervisionado.
- Expor o servidor para fora de `127.0.0.1` de forma permanente — qualquer
  exposição é temporária, via túnel, e só durante a validação.

Ver também: [roadmap](roadmap.md) · [demo local](demo-local.md) ·
[índice da documentação](index.md)
