"""Genie Conversation API — chat do App sobre o Genie space dedicado.

O space é criado pelo job pf_genie_setup (depois do deploy), então o ID é resolvido em runtime:
GENIE_SPACE_ID (se definido) ou busca pelo título GENIE_SPACE_TITLE entre os spaces que o SP
enxerga (o setup concede CAN_RUN ao SP do App).

Fluxo assíncrono para não estourar o timeout do proxy do Apps: `ask` envia a mensagem e espera
até ~WAIT_S; se o Genie ainda estiver trabalhando, devolve status pendente com os IDs e o
frontend continua via `poll`.
"""
import json
import os
import time
from typing import Any

from databricks.sdk.service.dashboards import GenieMessage, MessageStatus

from .config import get_workspace_client, get_workspace_host

GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")
GENIE_SPACE_TITLE = os.environ.get("GENIE_SPACE_TITLE", "Player Feedback — Genie")

# Espera server-side por request (o proxy do Databricks Apps corta requests longos).
WAIT_S = 25.0
MAX_ROWS = 200

# Usadas se o SP não puder ler o serialized_space (exige CAN_EDIT; o SP tem CAN_RUN).
FALLBACK_QUESTIONS = [
    "Quais jogos tiveram mais bug reports na semana passada?",
    "Como evoluiu o sentimento negativo de cada jogo nas últimas 4 semanas?",
    "Qual a nota do último relatório semanal de cada jogo?",
    "Qual a taxa de erro das chamadas de IA por modelo?",
    "Qual jogo teve a maior taxa de toxicidade na semana passada?",
    "Quais são os temas mais citados nos reviews negativos de cada jogo?",
]

_TERMINAL = {
    MessageStatus.COMPLETED,
    MessageStatus.FAILED,
    MessageStatus.CANCELLED,
    MessageStatus.QUERY_RESULT_EXPIRED,
}

_CACHE: dict[str, Any] = {"space": None}


class GenieNotConfigured(Exception):
    """Nenhum Genie space encontrado (pf_genie_setup ainda não rodou ou falta CAN_RUN)."""


def get_space() -> dict:
    """{space_id, title, description, url, sample_questions}. Cacheado após o 1º sucesso."""
    if _CACHE["space"]:
        return _CACHE["space"]

    w = get_workspace_client()
    space = None
    if GENIE_SPACE_ID:
        space = w.genie.get_space(space_id=GENIE_SPACE_ID)
    else:
        token = None
        while space is None:
            resp = w.genie.list_spaces(page_size=100, page_token=token)
            space = next((s for s in resp.spaces or [] if s.title == GENIE_SPACE_TITLE), None)
            token = resp.next_page_token
            if not token:
                break
    if space is None:
        raise GenieNotConfigured(
            f"Genie space '{GENIE_SPACE_TITLE}' não encontrado. Rode o job pf_genie_setup."
        )

    questions = FALLBACK_QUESTIONS
    try:
        full = w.genie.get_space(space_id=space.space_id, include_serialized_space=True)
        if full.serialized_space:
            parsed = json.loads(full.serialized_space)
            qs = ["".join(q.get("question", [])) for q in parsed.get("config", {}).get("sample_questions", [])]
            questions = [q for q in qs if q] or FALLBACK_QUESTIONS
    except Exception as e:  # noqa: BLE001
        print(f"[genie] serialized_space indisponível (usando perguntas padrão): {e}")

    _CACHE["space"] = {
        "space_id": space.space_id,
        "title": space.title,
        "description": space.description or "",
        "url": f"{get_workspace_host()}/genie/rooms/{space.space_id}",
        "sample_questions": questions,
    }
    return _CACHE["space"]


def ask(question: str, conversation_id: str | None = None) -> dict:
    """Inicia uma conversa (ou follow-up na mesma) e espera até WAIT_S pela resposta."""
    w = get_workspace_client()
    space_id = get_space()["space_id"]
    if conversation_id:
        sent = w.genie.create_message(
            space_id=space_id, conversation_id=conversation_id, content=question
        ).response
    else:
        sent = w.genie.start_conversation(space_id=space_id, content=question).response
    return _wait(space_id, sent.conversation_id, sent.message_id, deadline=time.time() + WAIT_S)


def poll(conversation_id: str, message_id: str) -> dict:
    """Continua esperando uma mensagem pendente (chamado pelo frontend em loop)."""
    space_id = get_space()["space_id"]
    return _wait(space_id, conversation_id, message_id, deadline=time.time() + WAIT_S)


def _wait(space_id: str, conversation_id: str, message_id: str, deadline: float) -> dict:
    w = get_workspace_client()
    delay = 1.0
    while True:
        msg = w.genie.get_message(
            space_id=space_id, conversation_id=conversation_id, message_id=message_id
        )
        if msg.status in _TERMINAL or time.time() + delay > deadline:
            return _serialize(space_id, msg)
        time.sleep(delay)
        delay = min(delay * 1.5, 4.0)


def _serialize(space_id: str, msg: GenieMessage) -> dict:
    status = msg.status.value if msg.status else "UNKNOWN"
    out: dict[str, Any] = {
        "conversation_id": msg.conversation_id,
        "message_id": msg.message_id,
        "status": status,
        "done": msg.status in _TERMINAL,
        "text": "",
        "sql": None,
        "query_description": None,
        "columns": [],
        "rows": [],
        "row_count": None,
        "truncated": False,
        "suggested_questions": [],
        "error": None,
    }
    if msg.status in (MessageStatus.FAILED, MessageStatus.CANCELLED):
        if msg.error and msg.error.error:
            print(f"[genie] mensagem {msg.message_id} falhou: {msg.error.error!r}")
        out["error"] = "O Genie não conseguiu responder a esta pergunta."
    if msg.status == MessageStatus.QUERY_RESULT_EXPIRED:
        out["error"] = "O resultado da consulta expirou — pergunte novamente."

    texts: list[str] = []
    query_attachment_id = None
    for att in msg.attachments or []:
        if att.text and att.text.content:
            texts.append(att.text.content)
        if att.query:
            out["sql"] = att.query.query
            out["query_description"] = att.query.description
            query_attachment_id = att.attachment_id
        if att.suggested_questions and att.suggested_questions.questions:
            out["suggested_questions"] = att.suggested_questions.questions
    out["text"] = "\n\n".join(texts) or (out["query_description"] or "")

    if msg.status == MessageStatus.COMPLETED and query_attachment_id:
        try:
            res = get_workspace_client().genie.get_message_attachment_query_result(
                space_id=space_id,
                conversation_id=msg.conversation_id,
                message_id=msg.message_id,
                attachment_id=query_attachment_id,
            )
            out.update(_rows(res.statement_response))
        except Exception as e:  # noqa: BLE001
            print(f"[genie] falha ao buscar resultado da query: {e!r}")
            out["error"] = out["error"] or "Não foi possível carregar o resultado da consulta."
    return out


def _rows(stmt) -> dict:
    """Converte o StatementResponse (formato JSON_ARRAY) em colunas + linhas (máx. MAX_ROWS)."""
    if not stmt or not stmt.manifest or not stmt.manifest.schema:
        return {}
    columns = [c.name for c in stmt.manifest.schema.columns or []]
    data = stmt.result.data_array if stmt.result and stmt.result.data_array else []
    total = stmt.manifest.total_row_count if stmt.manifest.total_row_count is not None else len(data)
    return {
        "columns": columns,
        "rows": [list(r) for r in data[:MAX_ROWS]],
        "row_count": total,
        "truncated": total > min(len(data), MAX_ROWS),
    }
