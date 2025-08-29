from __future__ import annotations
import os
import base64
from typing import Optional, Dict, Any

# Carrega .env sem sobrescrever variáveis já presentes
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

from openai import OpenAI


class OpenAIClient:
    
  
    """Wrapper simples para chat com OpenAI 1.x.

    
    Usa:
      - api_key passada no ``__init__`` ou ``OPENAI_API_KEY`` do ambiente.
    Modelo:
      - prioridade: parâmetro ``chat_model``
      - depois: ``OPENAI_MODEL`` ou ``OPENAI_CHAT_MODEL``
      - fallback: ``gpt-5-mini``
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
    
class LLM(OpenAIClient):
    """Cliente de LLM com utilidades de transcrição e OCR."""

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        """Envia bytes de áudio para transcrição via API."""
        model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        try:
            resp = self.client.audio.transcriptions.create(
                model=model,
                file=("audio", audio_bytes, mime_type),
            )
            return (getattr(resp, "text", "") or "").strip()
        except Exception:
            return ""

    def ocr_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        caption: Optional[str] = None,
    ) -> str:
        """Extrai texto de uma imagem usando modelo multimodal."""
        model = os.getenv("OPENAI_VISION_MODEL", self.chat_model)
        prompt = "Extraia todo o texto presente na imagem."
        if caption:
            prompt += f"\nLegenda: {caption}"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        try:
            resp = self.client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_image",
                                "image": {"base64": b64, "media_type": mime_type},
                            },
                        ],
                    }
                ],
                temperature=self.temperature,
            )
            return (getattr(resp, "output_text", "") or "").strip()
        except Exception:
            return ""


__all__ = ["OpenAIClient", "LLM"]