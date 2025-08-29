import logging
import mimetypes
from typing import Optional
import requests

from ..utils.openai_client import LLM

logger = logging.getLogger(__name__)

ALLOWED_AUDIO = {"audio/mpeg", "audio/ogg", "audio/m4a", "audio/wav", "audio/mp4", "audio/aac"}
ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

class MediaProcessor:
    """
    Responsável por baixar mídia (com URL fornecida pela Z-API), 
    e transformá-la em texto:
      - Áudio -> transcrição (OpenAI)
      - Imagem -> OCR/extração (OpenAI vision)
    """

    def __init__(self, llm: LLM, http_timeout: int = 20):
        self.llm = llm
        self.http_timeout = http_timeout

    def _download_bytes(self, url: str) -> tuple[bytes, Optional[str]]:
        """
        Baixa a mídia. Retorna (bytes, mime_type_detectado).
        Usa cabeçalho Content-Type se disponível; senão tenta pelo sufixo do arquivo.
        """
        r = requests.get(url, timeout=self.http_timeout)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type")
        if not content_type:
            # tenta inferir por extensão
            guess = mimetypes.guess_type(url)[0]
            content_type = guess or "application/octet-stream"
        return r.content, content_type

    def audio_to_text(self, audio_bytes: bytes, mime_type: str) -> str:
        """
        Envia os bytes de áudio para transcrição.
        """
        if mime_type not in ALLOWED_AUDIO:
            logger.warning("MIME de áudio não listado (%s). Tentando assim mesmo.", mime_type)
        return self.llm.transcribe_audio(audio_bytes, mime_type)

    def image_to_text(self, image_bytes: bytes, mime_type: str, caption: Optional[str]) -> str:
        """
        Faz OCR/extração semântica via modelo multimodal. 
        Inclui a 'caption' se o usuário tiver mandado junto.
        """
        if mime_type not in ALLOWED_IMAGE:
            logger.warning("MIME de imagem não listado (%s). Tentando assim mesmo.", mime_type)
        return self.llm.ocr_image(image_bytes, mime_type, caption)

    def process_media_to_text(self, media_url: str, media_type: str, media_mime: Optional[str], caption: Optional[str]) -> str:
        """
        Pipeline completo: baixa e converte para texto.
        """
        blob, detected = self._download_bytes(media_url)
        mt = media_mime or detected or "application/octet-stream"

        if media_type == "audio":
            text = self.audio_to_text(blob, mt)
            return text.strip()

        if media_type == "image":
            text = self.image_to_text(blob, mt, caption)
            return text.strip()

        # documentos (PDF) — opcional: você pode redirecionar para o indexador ou sumarizador
        raise ValueError(f"Tipo de mídia não suportado no webhook: {media_type}")