from __future__ import annotations

from typing import List, Dict


def handle_incoming(
    session_id: str,
    user_message: str,
    *,
    msg_repo,
    LLM,
    system_prompt: str,
) -> str:
    """Process an incoming user message and return the assistant response.

    Parameters
    ----------
    session_id:
        Identifier for the conversation session. Used to retrieve history and
        persist messages.
    user_message:
        Latest message sent by the user.
    msg_repo:
        Repository responsible for persisting and retrieving messages. It must
        implement ``listar_ultimas`` and ``save``.
    LLM:
        Large language model client with a ``chat`` method that accepts a list
        of messages.
    system_prompt:
        The system instruction passed as the first message to the LLM.
    """

    # Save the new user message so that history retrieval includes it.
    msg_repo.save(session_id, "user", user_message)

    # Retrieve the last N messages for context.
    history = msg_repo.listar_ultimas(session_id, n=20)

    # Build the message list: system message first, followed by history.
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})

    # Generate the assistant's response using the LLM.
    response = LLM.chat(messages)

    # Persist the assistant response.
    msg_repo.save(session_id, "assistant", response)

    return response