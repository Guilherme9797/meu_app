from __future__ import annotations
import os
from typing import Optional, Dict, Any

# Carrega .env sem sobrescrever variáveis já presentes
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

from openai import OpenAI


class OpenAIClient:
    """
    Wrapper simples para chat com OpenAI 1.x.
    Usa:
      - api_key passada no __init__, ou
      - OPENAI_API_KEY do ambiente (.env)
    Modelo:
      - prioridade: parâmetro chat_model
      - depois: OPENAI_MODEL (ex.: gpt-5-mini)
      - depois: OPENAI_CHAT_MODEL
      - fallback: gpt-4o-mini
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        chat_model: Optional[str] = None,
        temperature: float = 1.0,
    ) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY não definido — configure no .env ou passe api_key")
        # garante para libs que leem só do ambiente
        os.environ.setdefault("OPENAI_API_KEY", key)

        # aceita OPENAI_MODEL OU OPENAI_CHAT_MODEL
        model = (
            chat_model
            or os.getenv("OPENAI_MODEL")
            or os.getenv("OPENAI_CHAT_MODEL")
            or "gpt-4o-mini"
        )

        self.client = OpenAI(api_key=key)
        self.chat_model = model
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", str(temperature)))

        # log leve (só prefixo da key)
        try:
            import logging
            logging.getLogger("openai_client").info(
                "OpenAI key prefix: %s | model: %s",
                (key[:6] + "***"),
                self.chat_model,
            )
        except Exception:
            pass

    def chat(self, system: str, user: str, *, extra: Optional[Dict[str, Any]] = None) -> str:
        params: Dict[str, Any] = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.temperature != 1.0:
            params["temperature"] = self.temperature
        if extra:
            params.update(extra)

        resp = self.client.chat.completions.create(**params)
        choice = resp.choices[0]
        return (choice.message.content or "").strip()
