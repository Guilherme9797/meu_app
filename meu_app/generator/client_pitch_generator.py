# -*- coding: utf-8 -*-
"""Gerador de respostas comerciais curtas com CTA."""
from typing import Dict, Any, Optional

DEFAULT_BRANDING = {
    "firm_name": "Seu Escritório de Advocacia",
    "cta_phone": "(11) 99999-0000",
    "cta_whatsapp": "https://wa.me/55999990000",
    "cta_email": "contato@seuescritorio.com.br",
    "cta_city": "atuação nacional",
}

SYSTEM_PROMPT = (
    "Você é um ADVOGADO BRASILEIRO ESPECIALISTA. "
    "Responda SEMPRE em PT-BR, com linguagem simples, carismática, empática e objetiva. "
    "Trate quem pergunta como um potencial cliente. "
    "Traga soluções práticas e claras; explique os próximos passos; "
    "e convide a falar com o escritório (CTA). "
    "Evite juridiquês, evite respostas genéricas e evite longos avisos legais. "
    "Se faltar algum dado essencial, peça só o mínimo necessário em 1–2 bullets. "
    "Formate em seções curtas com bullets. "
)

USER_TEMPLATE = (
    "Pergunta do potencial cliente (copie a essência e responda de forma direta):\n"
    "«{user_question}»\n\n"
    "Instruções de estilo e objetivos:\n"
    "- Explique o que está acontecendo juridicamente em linguagem humana.\n"
    "- Traga 2–5 soluções/estratégias possíveis (com prós/cons e quando usar).\n"
    "- Diga o que o cliente pode fazer HOJE (checklist de provas e passos imediatos).\n"
    "- Argumente 3–5 vantagens de resolver com nosso escritório.\n"
    "- Termine com um CTA claro para contato (tel/WhatsApp/e-mail).\n"
    "- Máximo ~12 linhas úteis (seções curtas com bullets)."
)

CTA_FOOTER = (
    "\n\nEntre em contato agora:\n"
    "• Telefone: {cta_phone}\n"
    "• WhatsApp: {cta_whatsapp}\n"
    "• E-mail: {cta_email}\n"
    "• Atendimento: {cta_city}\n"
)


class ClientPitchGenerator:
    """
    Gera respostas 'comerciais' universais: advogado brasileiro, simples e carismático,
    propondo soluções e chamando para contato (CTA). Independe da área do direito.
    """

    def __init__(self, llm, logger, branding: Optional[Dict[str, str]] = None):
        self.llm = llm
        self.logger = logger
        self.branding = {**DEFAULT_BRANDING, **(branding or {})}

    def compose(self, user_message: str, extra_context: Optional[Dict[str, Any]] = None) -> str:
        system = SYSTEM_PROMPT
        user = USER_TEMPLATE.format(user_question=user_message)

        # logs úteis para depuração
        if self.logger:
            self.logger.info("ClientPitchGenerator: enviando prompt comercial direto ao LLM.")

        try:
            # Usa a interface de chat do seu wrapper LLM (ajuste nomes conforme seu wrapper)
            out = self.llm.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
                max_tokens=700,
                top_p=1.0,
            )
            text = out.strip()
        except Exception:
            if self.logger:
                self.logger.exception("Falha no LLM (ClientPitchGenerator).")
            # fallback minimalista, ainda com CTA:
            text = (
                "Entendi seu caso. Podemos atuar com uma estratégia sob medida, começando por reunir documentos "
                "básicos e definir a medida jurídica correta. Fale com a gente para avançar."
            )

        # anexa CTA padronizado
        text += CTA_FOOTER.format(**self.branding)
        # reforça marca (opcional, discreto)
        text = f"{self.branding['firm_name']}\n\n{text}"
        return text