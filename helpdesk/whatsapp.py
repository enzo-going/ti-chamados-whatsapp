"""Borda local da integração de mensagens (WhatsApp Cloud API).

Implementa as três peças que a integração real exige, todas **testáveis sem
rede** e sem credenciais:

- ``verify_webhook``: handshake de verificação do webhook (GET com
  ``hub.mode`` / ``hub.verify_token`` / ``hub.challenge``);
- ``valid_signature``: validação da assinatura ``X-Hub-Signature-256``
  (HMAC-SHA256 do corpo bruto com o app secret);
- ``extract_inbound_payloads``: payload de webhook da Cloud API → payloads
  neutros no formato do ``/inbound`` (``helpdesk/inbound.py``), aproveitando a
  idempotência existente (o id da mensagem vira ``event_id``);
- ``CloudApiTransport``: implementação de ``MessagingTransport`` para envio,
  com a função HTTP **injetável** — testes usam um fake e nenhuma chamada
  externa acontece sem um token real definido no ambiente.

Nada aqui abre conexão externa por conta própria. A conexão real (Fase 3 do
roadmap) continua condicionada à decisão da estratégia do número; o checklist
do que validar antes está em ``docs/pre-integracao.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from helpdesk import config

# Versão da Graph API usada na URL de envio; parametrizada no transporte.
DEFAULT_GRAPH_VERSION = "v23.0"

# Prefixo do cabeçalho de assinatura enviado pela plataforma.
_SIGNATURE_PREFIX = "sha256="

# Assinatura da função HTTP injetável: (url, headers, corpo) -> (status, resposta).
HttpPost = Callable[[str, Mapping[str, str], bytes], tuple[int, str]]


class InvalidWebhookPayload(ValueError):
    """Payload de webhook estruturalmente inválido (não parece Cloud API)."""


class TransportError(RuntimeError):
    """Falha no envio de mensagem pela API (status HTTP de erro)."""


# --------------------------------------------------------------------------- #
# Verificação do webhook (handshake GET)
# --------------------------------------------------------------------------- #


def verify_webhook(params: Mapping[str, str], verify_token: str) -> str | None:
    """Valida o handshake de verificação e devolve o challenge a ecoar.

    Devolve ``None`` quando a requisição não é um handshake válido (modo
    diferente de ``subscribe`` ou token não confere) — o chamador responde 403.
    A comparação do token usa ``hmac.compare_digest`` (tempo constante).
    """
    if not verify_token:
        return None
    if params.get("hub.mode") != "subscribe":
        return None
    received = params.get("hub.verify_token") or ""
    if not hmac.compare_digest(received, verify_token):
        return None
    return params.get("hub.challenge", "")


# --------------------------------------------------------------------------- #
# Assinatura do corpo (X-Hub-Signature-256)
# --------------------------------------------------------------------------- #


def valid_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Confere a assinatura HMAC-SHA256 do corpo bruto da requisição.

    O cabeçalho tem o formato ``sha256=<hex>``. Sem app secret configurado ou
    sem cabeçalho, a resposta é ``False`` (fail closed): nenhum payload entra
    sem assinatura válida.
    """
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    received = signature_header[len(_SIGNATURE_PREFIX):].strip().lower()
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


# --------------------------------------------------------------------------- #
# Payload do webhook → payloads neutros do /inbound
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WebhookExtraction:
    """Resultado da extração: payloads aproveitáveis + o que foi ignorado.

    ``ignored`` guarda apenas **motivos** (texto curto), nunca conteúdo de
    mensagem, telefone ou nome — pode ir para log/resposta sem vazar dados.
    """

    payloads: list[dict[str, object]]
    ignored: list[str]


def extract_inbound_payloads(payload: object) -> WebhookExtraction:
    """Converte um payload de webhook da Cloud API em payloads do ``/inbound``.

    Cada mensagem de texto vira um payload neutro (``event_id`` = id da
    mensagem, o que liga a idempotência existente às reentregas da
    plataforma). Recibos de status (entrega/leitura) e tipos não suportados
    são ignorados com um motivo — o webhook responde 200 mesmo assim, como a
    plataforma espera, sem processá-los.
    """
    if not isinstance(payload, Mapping):
        raise InvalidWebhookPayload("payload deve ser um objeto JSON")
    entries = payload.get("entry") or []
    if not isinstance(entries, list):
        raise InvalidWebhookPayload("campo 'entry' deve ser uma lista")

    payloads: list[dict[str, object]] = []
    ignored: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            ignored.append("entry malformada")
            continue
        changes = entry.get("changes") or []
        if not isinstance(changes, list):
            ignored.append("campo 'changes' malformado")
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, Mapping) else None
            if not isinstance(value, Mapping):
                ignored.append("change sem 'value'")
                continue
            _extract_from_value(value, payloads, ignored)
    return WebhookExtraction(payloads=payloads, ignored=ignored)


def _extract_from_value(
    value: Mapping[str, object],
    payloads: list[dict[str, object]],
    ignored: list[str],
) -> None:
    names = _contact_names(value)

    statuses = value.get("statuses")
    if isinstance(statuses, list) and statuses:
        ignored.append(f"{len(statuses)} recibo(s) de status (entrega/leitura)")

    messages = value.get("messages") or []
    if not isinstance(messages, list):
        ignored.append("campo 'messages' malformado")
        return
    for message in messages:
        if not isinstance(message, Mapping):
            ignored.append("mensagem malformada")
            continue
        message_id = message.get("id")
        sender = message.get("from")
        if not isinstance(message_id, str) or not isinstance(sender, str):
            ignored.append("mensagem sem 'id'/'from'")
            continue
        kind = message.get("type")
        if kind != "text":
            ignored.append(f"tipo não suportado: {kind!r}")
            continue
        text = message.get("text")
        body = text.get("body") if isinstance(text, Mapping) else None
        if not isinstance(body, str) or not body.strip():
            ignored.append("mensagem de texto sem corpo")
            continue
        neutral: dict[str, object] = {
            "event_id": message_id,
            "sender": sender,
            "text": body,
        }
        if sender in names:
            neutral["sender_name"] = names[sender]
        timestamp = _epoch_to_iso(message.get("timestamp"))
        if timestamp is not None:
            neutral["timestamp"] = timestamp
        payloads.append(neutral)


def _contact_names(value: Mapping[str, object]) -> dict[str, str]:
    """Mapa wa_id → nome de perfil, a partir do bloco ``contacts``."""
    names: dict[str, str] = {}
    contacts = value.get("contacts")
    if not isinstance(contacts, list):
        return names
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        wa_id = contact.get("wa_id")
        profile = contact.get("profile")
        name = profile.get("name") if isinstance(profile, Mapping) else None
        if isinstance(wa_id, str) and isinstance(name, str) and name.strip():
            names[wa_id] = name
    return names


def _epoch_to_iso(value: object) -> str | None:
    """Timestamp epoch (string de segundos) → ISO 8601 UTC, ou None."""
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    return None


# --------------------------------------------------------------------------- #
# Transporte de saída (envio de respostas)
# --------------------------------------------------------------------------- #


class CloudApiTransport:
    """``MessagingTransport`` de envio pela Cloud API, com HTTP injetável.

    A função HTTP entra pelo construtor: testes passam um fake e nenhuma
    requisição externa acontece. O token nunca aparece em ``repr``/logs — ele
    só entra no cabeçalho ``Authorization`` da chamada.
    """

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        http_post: HttpPost | None = None,
        graph_version: str = DEFAULT_GRAPH_VERSION,
    ) -> None:
        if not token or not phone_number_id:
            raise ValueError("token e phone_number_id são obrigatórios")
        self._token = token
        self.phone_number_id = phone_number_id
        self.graph_version = graph_version
        self._http_post: HttpPost = http_post or _urllib_post

    @classmethod
    def from_env(cls, http_post: HttpPost | None = None) -> "CloudApiTransport":
        """Constrói a partir das variáveis de ambiente reservadas.

        Falha listando os **nomes** das variáveis ausentes — valores nunca
        entram em mensagens de erro.
        """
        token = config.whatsapp_token()
        phone_number_id = config.whatsapp_phone_number_id()
        missing = [
            name
            for name, value in (
                (config.WHATSAPP_TOKEN_ENV, token),
                (config.WHATSAPP_PHONE_NUMBER_ID_ENV, phone_number_id),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "variáveis de ambiente ausentes para o transporte: "
                + ", ".join(missing)
            )
        assert token is not None and phone_number_id is not None
        return cls(token=token, phone_number_id=phone_number_id, http_post=http_post)

    def send(self, recipient: str, text: str) -> None:
        url = (
            f"https://graph.facebook.com/{self.graph_version}/"
            f"{self.phone_number_id}/messages"
        )
        body = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        status, response = self._http_post(url, headers, body)
        if status >= 300:
            # Sem destinatário nem token na mensagem: só status e o início da
            # resposta da API (que não contém credenciais).
            raise TransportError(
                f"envio recusado pela API (HTTP {status}): {response[:200]}"
            )

    def __repr__(self) -> str:  # nunca incluir o token
        return (
            f"CloudApiTransport(phone_number_id={self.phone_number_id!r}, "
            f"graph_version={self.graph_version!r})"
        )


def _urllib_post(url: str, headers: Mapping[str, str], body: bytes) -> tuple[int, str]:
    """Implementação padrão do envio HTTP (usada só fora dos testes)."""
    request = urllib.request.Request(
        url, data=body, headers=dict(headers), method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
