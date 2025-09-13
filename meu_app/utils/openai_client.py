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
    from openai import OpenAI, BadRequestError

except Exception:  # pragma: no cover - ambiente sem SDK
    OpenAI = None
    class BadRequestError(Exception):  # pragma: no cover - stub para testes
        pass


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
            or "gpt-5-mini"
        )

        if OpenAI is None:  # pragma: no cover - ausência do SDK
            raise RuntimeError("SDK OpenAI não disponível. Instale 'openai' >= 1.0.")

        self.client = OpenAI(api_key=key)
        self.chat_model = model
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", str(temperature)))
        self._supports_temperature = True
        self._supports_top_p = True
        self._supports_presence_penalty = True
    
    def _token_key(self) -> str:
        """Retorna o nome do parâmetro de limite de tokens suportado."""
        model = (self.chat_model or "").lower()
        if any(m in model for m in ("gpt-5-mini", "gpt-4o", "gpt-4.1")):
            return "max_completion_tokens"
        return "max_tokens"

    def _chat_create(self, params: Dict[str, Any]) -> Any:
        """Executa a chamada ao chat com fallbacks leves."""
        try:
            return self.client.chat.completions.create(**params)
        except BadRequestError as e:
            msg = getattr(e, "message", str(e))
            lower = msg.lower()
            if (
                "temperature" in params
                and "temperature" in lower
                and ("unsupported" in lower or "only the default" in lower)
            ):
                self._supports_temperature = False
                params.pop("temperature", None)
                logging.warning("Modelo sem suporte a temperature; repetindo sem o parâmetro.")
                return self._chat_create(params)
            if (
                "top_p" in params
                and "top_p" in lower
                and ("unsupported" in lower or "not supported" in lower)
            ):
                self._supports_top_p = False
                params.pop("top_p", None)
                logging.warning("Modelo sem suporte a top_p; repetindo sem o parâmetro.")
                return self._chat_create(params)
            if (
                "presence_penalty" in params
                and "presence_penalty" in lower
                and ("unsupported" in lower or "not supported" in lower)
            ):
                self._supports_presence_penalty = False
                params.pop("presence_penalty", None)
                logging.warning(
                    "Modelo sem suporte a presence_penalty; repetindo sem o parâmetro."
                )
                return self._chat_create(params)
            logging.error("OpenAI 400: %s", msg)
            if (
                "max_tokens" in params
                and ("max_tokens" in lower or "unsupported parameter" in lower)
            ):
                max_tokens = params.pop("max_tokens", None)
                r = self.client.responses.create(
                    model=params.get("model", self.chat_model),
                    input=[
                        {"role": m["role"], "content": m["content"]}
                        for m in params["messages"]
                    ],
                    temperature=params.get("temperature"),
                    max_output_tokens=max_tokens,
                )
                return type(
                    "RespWrap",
                    (),
                    {
                        "choices": [
                            type(
                                "Choice",
                                (),
                                {
                                    "message": type(
                                        "Msg", (), {"content": getattr(r, "output_text", "")}
                                    )()
                                },
                            )()
                        ]
                    },
                )()
            alt_model = "gpt-5-mini"
            if params.get("model") != alt_model:
                params["model"] = alt_model
                return self._chat_create(params)
            raise
        except Exception as e:  # pragma: no cover - depende de modelo externo
            msg = str(e)
            lower = msg.lower()
            if (
                "temperature" in params
                and "temperature" in lower
                and ("unsupported" in lower or "only the default" in lower)
            ):
                self._supports_temperature = False
                params.pop("temperature", None)
                logging.warning("Modelo sem suporte a temperature; repetindo sem o parâmetro.")
                return self._chat_create(params)
            if (
                "top_p" in params
                and "top_p" in lower
                and ("unsupported" in lower or "not supported" in lower)
            ):
                self._supports_top_p = False
                params.pop("top_p", None)
                logging.warning("Modelo sem suporte a top_p; repetindo sem o parâmetro.")
                return self._chat_create(params)
            if (
                "presence_penalty" in params
                and "presence_penalty" in lower
                and ("unsupported" in lower or "not supported" in lower)
            ):
                self._supports_presence_penalty = False
                params.pop("presence_penalty", None)
                logging.warning(
                    "Modelo sem suporte a presence_penalty; repetindo sem o parâmetro."
                )
                return self._chat_create(params)
            raise

    def chat(
        self,
        system: Optional[str] = None,
        user: Optional[str] = None,
        *,
        messages: Optional[List[Dict[str, str]]] = None,
        extra: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Envia um conjunto de mensagens ao modelo.

        Aceita tanto parâmetros ``system``/``user`` (compatibilidade com a versão
        anterior) quanto uma lista ``messages`` já pronta, no formato da API do
        OpenAI. Parâmetros como ``temperature`` e limites de tokens podem ser
        passados diretamente ou via ``extra``.
        """

        if messages is None:
            if system is None or user is None:
                raise TypeError("Forneça 'messages' ou 'system' e 'user'.")
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]

        params: Dict[str, Any] = {"model": self.chat_model, "messages": messages}
        extra_params = dict(extra or {})
        temp = (
            temperature
            if temperature is not None
            else extra_params.pop("temperature", self.temperature)
        )
        if temp != 1.0 and self._supports_temperature:
            params["temperature"] = temp

        top_p_val = kwargs.pop("top_p", extra_params.pop("top_p", None))
        if top_p_val is not None and self._supports_top_p:
            params["top_p"] = top_p_val

        presence_val = kwargs.pop(
            "presence_penalty", extra_params.pop("presence_penalty", None)
        )
        if presence_val is not None and self._supports_presence_penalty:
            params["presence_penalty"] = presence_val
            
        token_key = self._token_key()
        
        if max_tokens is not None:
            params[token_key] = max_tokens
        elif max_completion_tokens is not None:
            params["max_completion_tokens"] = max_completion_tokens
        else:
            mt = extra_params.pop("max_tokens", None)
            mc = extra_params.pop("max_completion_tokens", None)
            if mt is not None:
                params[token_key] = mt
            elif mc is not None:
                params["max_completion_tokens"] = mc

        if extra_params:
            params.update(extra_params)
        if kwargs:
            params.update(kwargs)

        try:
            resp = self._chat_create(params)
        except Exception as e:  # pragma: no cover - depende de modelo externo
            msg = str(e).lower()
            if (
                token_key == "max_tokens"
                and "max_tokens" in msg
                and "max_completion_tokens" in msg
                and token_key in params
            ):
                mt = params.pop(token_key)
                params["max_completion_tokens"] = mt
                resp = self._chat_create(params)
            else:
                raise
            
        return (resp.choices[0].message.content or "").strip()


class Embeddings:
    """Utilitário de embeddings usando o SDK 1.x."""

    def __init__(self, api_key: Optional[str] = None, *, model: Optional[str] = None) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY não definido — configure no .env ou passe api_key")
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
        if temp != 1.0 and self._supports_temperature:
            params["temperature"] = temp

        token_key = self._token_key()

        def _call_with_token_key(tok: str):
            p = dict(params)
            p[tok] = max_tokens
            return self._chat_create(p)
        
        try:
            resp = _call_with_token_key(token_key)
        except Exception as e:
            msg = str(e).lower()
            if (
                token_key == "max_tokens"
                and "max_tokens" in msg
                and "max_completion_tokens" in msg
            ):
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
                if temp != 1.0 and self._supports_temperature:
                    params_retry["temperature"] = temp
                def _call_retry(tok: str):
                    p = dict(params_retry)
                    p[tok] = max_tokens
                    return self._chat_create(p)
                try:
                    resp2 = _call_retry(token_key)
                except Exception as e2:
                    msg2 = str(e2).lower()
                    if (
                        token_key == "max_tokens"
                        and "max_tokens" in msg2
                        and "max_completion_tokens" in msg2
                    ):
                        resp2 = _call_retry("max_completion_tokens")
                    else:
                        raise
                text = (resp2.choices[0].message.content or "").strip()
            except Exception:
                logging.getLogger("openai_client").exception(
                    "Retry anti-eco falhou."
                )

        return text

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-5-mini-transcribe")
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
            temp = self.temperature
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
                temperature=temp if (self._supports_temperature and temp != 1.0) else None,
            )
            return (getattr(resp, "output_text", "") or "").strip()
        except Exception:  # pragma: no cover - depende de serviço externo
            
            return ""
        
