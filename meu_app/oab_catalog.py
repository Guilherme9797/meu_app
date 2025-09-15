from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from rapidfuzz import fuzz, process  # type: ignore
except Exception:  # pragma: no cover - fallback leve
    fuzz = None
    process = None
    from difflib import SequenceMatcher

@dataclass
class OABItem:
    code: str
    name: str
    min_fee: float
    tags: List[str]

CATALOG: Dict[str, OABItem] = {
    # Trânsito (exemplos do seu pricing atual)
    "TRÂNSITO_DEFESA_PREVIA": OABItem("TRÂNSITO_DEFESA_PREVIA","Defesa Prévia Trânsito",419.08,["trânsito","defesa prévia","recurso inicial","ait"]),
    "TRÂNSITO_JARI": OABItem("TRÂNSITO_JARI","Recurso JARI",628.62,["trânsito","jari","recurso 1ª instância"]),
    "TRÂNSITO_CETRAN": OABItem("TRÂNSITO_CETRAN","Recurso CETRAN",942.93,["trânsito","cetran","segunda instância"]),

    # Penal JECRIM (valores ilustrativos → Tavily pode sobrepor)
    "PENAL_JECRIM_PRELIMINAR": OABItem("PENAL_JECRIM_PRELIMINAR","Audiência Preliminar JECRIM",1200.00,["penal","jecrim","audiência preliminar","ameaça","art.147"]),
    "PENAL_ACOMP_INQUERITO": OABItem("PENAL_ACOMP_INQUERITO","Acompanhamento de TCO/Inquérito",1000.00,["penal","tco","inquérito","delegacia"]),

    # Genéricos
    "CONSULTA_INICIAL": OABItem("CONSULTA_INICIAL","Consulta Estratégica",300.00,["consulta","orientação","estratégia"]),
    "ACOMPANHAMENTO_INICIAL": OABItem("ACOMPANHAMENTO_INICIAL","Acompanhamento Inicial/Protocolos",800.00,["inicial","protocolo","medida urgente"]),
}

def search_codes_by_label(label: str, limit: int = 3) -> List[OABItem]:
    corpus = {k: (v.name + " " + " ".join(v.tags)).lower() for k, v in CATALOG.items()}
    out: List[OABItem] = []
    if process and fuzz:
        matches = process.extract(label.lower(), corpus, scorer=fuzz.WRatio, limit=limit)
        for (code, score, _meta) in matches:
            if score >= 70:
                out.append(CATALOG[code])
        return out

    # fallback básico usando difflib
    def _score(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100

    scored = sorted(
        ((code, _score(label.lower(), blob)) for code, blob in corpus.items()),
        key=lambda it: it[1],
        reverse=True,
    )
    for code, score in scored[:limit]:
        if score >= 60:
            out.append(CATALOG[code])
    return out

def get_item(code: str) -> Optional[OABItem]:
    return CATALOG.get(code)