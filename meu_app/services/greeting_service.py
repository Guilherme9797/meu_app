from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


def is_greeting(text: str) -> bool:
    """Detecção leve de saudações em PT-BR.

    Considera algumas expressões comuns no início da mensagem.
    """
    if not text:
        return False
    txt = text.strip().lower()
    greetings: Iterable[str] = (
        "oi",
        "oie",
        "e aí",
        "iai",
        "olá",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "como você está",
        "como voce esta",
        "como vc tá",
        "como vc ta",
        "tudo bem",
        "como anda as coisas",
    )
    return any(txt.startswith(g) for g in greetings)


def generate_human_greeting(
    llm: Optional[object],
    *,
    name: str | None,
    brand: str,
    now_local: datetime,
) -> str:
    """Gera uma saudação simples.

    O parâmetro ``llm`` é aceito apenas para compatibilidade de interface com a
    implementação completa usada em produção.  Aqui retornamos uma frase
    determinística para que a aplicação possa iniciar mesmo quando as
    dependências do LLM não estão disponíveis (por exemplo durante os testes).
    """

    nome = (name or "cliente").strip()
    saudacao = "Olá" if is_greeting("oi") else "Olá"  # reuso leve da função
    return f"{saudacao} {nome}, bem-vindo à {brand}!"