from __future__ import annotations
import base64
import logging
import os
from typing import Any, Dict, List, Optional, Union

import numpy as np

# Carrega .env sem sobrescrever variáveis já presentes
try:  # pragma: no cover - utilitário
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:  # pragma: no cover - opcional
    pass

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - ambiente sem SDK
    OpenAI = None

APOLOGY_MESSAGE = "Desculpe, ocorreu um erro ao gerar a resposta."

__all__ = ["OpenAIClient", "Embeddings", "LLM"]


class OpenAIClient:
    """Wrapper leve para a API de chat do OpenAI SDK v1."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        chat_model: Optional[str] = None,
        temperature: float = 1.0,
    ) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY não definido — configure no .env ou passe api_key"
            )
        os.environ.setdefault("OPENAI_API_KEY", key)

        model = (
            chat_model
            or os.getenv("OPENAI_MODEL")
            or os.getenv("OPENAI_CHAT_MODEL")
            or "gpt-4o-mini"
        )

        if OpenAI is None:  # pragma: no cover - ausência do SDK
            raise RuntimeError("SDK OpenAI não disponível. Instale 'openai' >= 1.0.")

        self.client = OpenAI(api_key=key)
        self.chat_model = model
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", str(temperature)))
    
    
    def chat(self, system: str, user: str, *, extra: Optional[Dict[str, Any]] = None) -> str:
        """Envia prompt com mensagens de sistema e usuário."""
        params: Dict[str, Any] = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        extra = dict(extra or {})
        temp = extra.pop("temperature", self.temperature)
        if temp != 1.0:
            params["temperature"] = temp
        if extra:
            params.update(extra)
        resp = self.client.chat.completions.create(**params)
        return (resp.choices[0].message.content or "").strip()


class Embeddings:
    """Utilitário de embeddings usando o SDK 1.x."""

    def __init__(self, api_key: Optional[str] = None, *, model: Optional[str] = None) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY não definido — configure no .env ou passe api_key")
            raise RuntimeError(
                "OPENAI_API_KEY não definido — configure no .env ou passe api_key"
            )
        os.environ.setdefault("OPENAI_API_KEY", key)

        if OpenAI is None:  # pragma: no cover
            raise RuntimeError("SDK OpenAI não disponível. Instale 'openai' >= 1.0.")

        self.client = OpenAI(api_key=key)
        self.model = model or os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
    


    def embed(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """Gera embeddings para uma string ou lista de strings."""
        inputs = [texts] if isinstance(texts, str) else list(texts)
        resp = self.client.embeddings.create(model=self.model, input=inputs)
        vecs = [np.array(item.embedding, dtype="float32") for item in resp.data]
        if isinstance(texts, str):
            return vecs[0].reshape(1, -1)
        return vecs


class LLM(OpenAIClient):
    """Cliente de LLM com utilidades extras (transcrição/OCR)."""
    
    def generate(
        self,
        prompt: Union[str, List[Dict[str, str]]],
        *,
        temperature: Optional[float] = None,
        system: Optional[str] = None,
        max_tokens: int = 600,
    ) -> str:
        """Gera resposta a partir de um prompt simples ou lista de mensagens."""
        if isinstance(prompt, str):
            messages: List[Dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            prompt_for_echo = prompt.strip()
        else:
            messages = prompt
            prompt_for_echo = " ".join(
                m.get("content", "") for m in prompt if m.get("role") == "user"
            ).strip()


        params: Dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
            
        }

        temp = self.temperature if temperature is None else temperature
        if temp != 1.0:
            params["temperature"] = temp

        resp = self.client.chat.completions.create(**params)
        def _call_with_token_key(token_key: str):
            p = dict(params)
            p[token_key] = max_tokens
            return self.client.chat.completions.create(**p)

        try:
            resp = _call_with_token_key("max_tokens")
        except Exception as e:
            msg = str(e).lower()
            if "max_tokens" in msg and "max_completion_tokens" in msg:
                resp = _call_with_token_key("max_completion_tokens")
            else:
                raise
            
        text = (resp.choices[0].message.content or "").strip()

        if text.strip() == prompt_for_echo and isinstance(prompt, str):
            try:
                params_retry: Dict[str, Any] = {
                    "model": self.chat_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Você é um advogado brasileiro. Responda de forma prática, sem ecoar.",
                        },
                        {"role": "user", "content": prompt_for_echo},
                    ],
                }
                if temp != 1.0:
                    params_retry["temperature"] = temp
                try:
                    resp2 = self.client.chat.completions.create(
                        **{**params_retry, "max_tokens": max_tokens}
                    )
                except Exception as e2:
                    msg2 = str(e2).lower()
                    if "max_tokens" in msg2 and "max_completion_tokens" in msg2:
                        resp2 = self.client.chat.completions.create(
                            **{**params_retry, "max_completion_tokens": max_tokens}
                        )
                    else:
                        raise
                text = (resp2.choices[0].message.content or "").strip()
            except Exception:
                logging.getLogger("openai_client").exception(
                    "Retry anti-eco falhou."
                )

        return text

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        try:
            resp = self.client.audio.transcriptions.create(
                model=model,
                file=("audio", audio_bytes, mime_type),
            )
            return (getattr(resp, "text", "") or "").strip()
        except Exception:  # pragma: no cover - depende de serviço externo
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
                temperature=temp if (temp := self.temperature) != 1.0 else None,
            )
            return (getattr(resp, "output_text", "") or "").strip()
        except Exception:  # pragma: no cover - depende de serviço externo
            
            return ""
        
        