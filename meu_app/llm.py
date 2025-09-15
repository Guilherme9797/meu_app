import os, json
from typing import Dict, Any
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # ou o que estiver usando

def llm_json(system: str, user: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chama OpenAI e tenta validar contra o schema simples (best effort).
    Se vier lixo, devolve um esqueleto padrão.
    """
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role":"system","content":system},
            {"role":"user","content":user}
        ],
        "temperature": 0.3
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=20)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
    except Exception:
        data = {}
    # validação mínima
    if "required_slots" not in data or "questions" not in data or "pricing_services" not in data:
        data.setdefault("required_slots", ["prazo","documentos","objetivo","orçamento"])
        data.setdefault("questions", {
            "prazo":"Existe algum prazo/audiência? Qual data?",
            "documentos":"Consegue enviar os documentos (PDF/foto)?",
            "objetivo":"Qual seu objetivo imediato?",
            "orçamento":"Prefere à vista ou parcelado?"
        })
        data.setdefault("pricing_services", ["Consulta Estratégica","Acompanhamento Inicial"])
        data.setdefault("cta", "Posso iniciar hoje. Prefere essencial ou intermediário?")
    return data

