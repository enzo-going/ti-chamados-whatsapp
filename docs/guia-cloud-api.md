---
tags: [helpdesk, integracao, guia, whatsapp]
---

# Guia prático: criar o app na Meta e validar com o número de teste

Passo a passo **para o dia da validação** da Fase 3: criar o app na plataforma da
Meta (WhatsApp Cloud API) e fazer um teste de ponta a ponta com o **número de
teste gratuito**, sem comprometer nenhum número real. Complementa o
[checklist de pré-integração](pre-integracao.md) (pré-voo + conceitos) com os
passos concretos.

> ⚠️ Só execute quando a Fase 3 for liberada (decisão da estratégia do número —
> ver [roadmap](roadmap.md)). Nada aqui entra no repositório: tokens, ids e
> números ficam só no seu ambiente local. A interface da Meta muda de tempos em
> tempos — os nomes podem variar um pouco, mas a sequência é esta.

## 0. Pré-requisitos (uma vez)

- Conta no **Meta for Developers** (`developers.facebook.com`), com login Facebook.
- Um **Meta Business Manager / portfólio de negócios** (`business.facebook.com`).
  A **verificação de negócio** só é exigida para liberar **limites maiores** —
  para o teste com número de teste, não precisa.

## 1. Criar o app e adicionar o WhatsApp

1. Meta for Developers → **Meus Apps** → **Criar app**.
2. Escolha o tipo voltado a **Empresa / Business** (conforme a tela do momento).
3. No painel do app: **Adicionar produto** → **WhatsApp** → **Configurar**.
4. Associe a uma **conta Business** (a do passo 0). A Meta cria automaticamente
   uma **WABA de teste** e um **número de teste**.

## 2. Coletar as credenciais (painel WhatsApp → "API Setup / Primeiros passos")

Anote **fora do repositório** (ex.: um gerenciador de senhas). Cada item vira uma
variável de ambiente do nosso projeto:

| Na Meta | Onde fica | Nossa variável |
|---|---|---|
| Token de acesso (**temporário**, ~24h) | WhatsApp → API Setup | `WHATSAPP_TOKEN` |
| Phone number ID (do número de teste) | WhatsApp → API Setup | `WHATSAPP_PHONE_NUMBER_ID` |
| App Secret | Configurações do app → **Básico** | `WHATSAPP_APP_SECRET` |
| Verify token (**você inventa** uma string secreta) | — | `WHATSAPP_VERIFY_TOKEN` |

Ainda na API Setup, **cadastre os destinatários de teste** (até 5): adicione o
**seu próprio número** e confirme o código. *(Sem isso, o número de teste não
consegue te responder — ele só fala com números autorizados.)*

## 3. Apontar as variáveis e subir o servidor

No terminal (as variáveis ficam só na sessão; nada vai para o git):

```powershell
$env:WHATSAPP_TOKEN = "..."
$env:WHATSAPP_PHONE_NUMBER_ID = "..."
$env:WHATSAPP_APP_SECRET = "..."
$env:WHATSAPP_VERIFY_TOKEN = "uma-string-secreta-que-voce-escolheu"

python -m helpdesk.config check                 # confirma presença, sem mostrar valores
python -m helpdesk.http_app --db teste.sqlite3 --transport cloud-api
```

O resumo de inicialização deve mostrar as rotas `/webhook` **ativas** e o
transporte **`cloud-api`**.

## 4. Expor o `127.0.0.1` por um túnel HTTPS temporário

O webhook da Meta precisa de uma URL **HTTPS pública**. O servidor continua
ligado só em loopback; o túnel é a única porta de entrada e **morre com o teste**.
Use qualquer um:

```
ngrok http 8000
# ou
cloudflared tunnel --url http://127.0.0.1:8000
```

Anote a URL `https://...` que o túnel exibir.

## 5. Registrar o webhook na Meta

1. Painel WhatsApp → **Configuration / Webhook** → **Editar**.
2. **Callback URL** = `https://<sua-url-de-tunel>/webhook`.
3. **Verify token** = o mesmo valor de `WHATSAPP_VERIFY_TOKEN`.
4. Salvar — a Meta faz um **GET de verificação** (handshake), que deve passar de
   primeira (é o `verify_webhook` do nosso `helpdesk/whatsapp.py`).
5. Em **Webhook fields**, **inscreva o campo `messages`** (é o que entrega as
   mensagens recebidas).

## 6. Teste de fumaça (ponta a ponta)

1. Do **seu celular** (o número cadastrado no passo 2), mande uma mensagem para o
   **número de teste** — ex.: "a impressora do RH parou".
2. Confira, em ordem:
   - **chamado criado** — o log do servidor mostra `/inbound: chamado #N (novo chamado)`;
   - **resposta automática** chega no seu WhatsApp;
   - **painel** atualizado em `http://127.0.0.1:8000/dashboard`;
   - mande **o mesmo texto de novo** → vira **follow-up** (log: `follow-up anexado`,
     sem duplicar). Esse é o desfecho explícito da decisão 20.

## 7. Encerramento (higiene)

- Derrube o túnel.
- **Revogue/rotacione** o token de teste na Meta.
- Limpe as variáveis do ambiente (feche o terminal, ou
  `Remove-Item Env:WHATSAPP_TOKEN, Env:WHATSAPP_PHONE_NUMBER_ID, Env:WHATSAPP_APP_SECRET, Env:WHATSAPP_VERIFY_TOKEN`).

## Depois do teste — caminho para produção

Quando a validação passar e a **estratégia do número** estiver decidida:

- **número de produção** — linha nova dedicada (opção A) ou migrar a atual
  (opção B); como o número funciona está em [pré-integração](pre-integracao.md);
- **token permanente** via *usuário de sistema* (o token da API Setup é temporário);
- **verificação de negócio** na Business Manager para liberar limites maiores;
- **nome de exibição** do número aprovado pela Meta.

Ver também: [pré-integração](pre-integracao.md) · [roadmap](roadmap.md) ·
[risco de banimento](riscos-banimento.md) · [mapa](mapa.md) ·
[índice da documentação](index.md)
