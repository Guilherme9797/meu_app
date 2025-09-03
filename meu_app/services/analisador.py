from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
from ..utils.openai_client import LLM

# ------------------------
# Analisador de problemas
# ------------------------

class AnalisadorDeProblemas:
    """Gera uma descrição resumida do problema a partir do histórico."""

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def identificar_problema(self, historico: List[Dict[str, str]]) -> str:
        linhas = []
        for msg in historico:
            autor = msg.get("autor") or ""
            texto = msg.get("mensagem") or ""
            linhas.append(f"{autor}: {texto}")
        user = "\n".join(linhas)
        system = (
            "Você é um assistente jurídico e deve identificar, em uma frase,"
            " qual é o problema apresentado pelo cliente."
        )
        return self.llm.chat(system=system, user=user)

# ------------------------
# Taxonomia simples de temas e intenções
# ------------------------

THEMES = {
    "familia": [
        r"\bdiv[oó]rcio\b", r"\bguarda\b", r"\bvisita[s]?\b", r"\bpens[aã]o\b", r"\balimentos\b",
        r"\buni[aã]o estável\b", r"\bregime de bens\b", r"\bpartilha\b"
    ],
    "sucessoes": [
        r"\binvent[aá]rio\b", r"\bheran[çc]a\b", r"\btestamento\b", r"\barrolamento\b", r"\bsobrepartilha\b"
    ],
    "contratos": [
        r"\bcontrato\b", r"\bcl[aá]usula\b", r"\brescis[aã]o\b", r"\bmulta\b", r"\binadimpl[eê]ncia\b",
        r"\bcompra e venda\b", r"\bloc[aã]o\b", r"\bprestac[aã]o de servi[cç]os\b"
    ],
    "imobiliario": [
        r"\bposse\b", r"\busucapi[aã]o\b", r"\bdespejo\b", r"\bcondom[ií]nio\b", r"\biptu\b", r"\baluguel\b",
        r"\b[dv]is[aã]o de terra\b", r"\bregistro de im[oó]vel\b"
    ],
    "empresarial": [
        r"\bsociedade\b", r"\bcontrato social\b", r"\bquotas?\b", r"\bmarca\b", r"\bnome empresarial\b"
    ],
    "tributario": [
        r"\btribut[oos]?\b", r"\bimposto[s]?\b", r"\bicms\b", r"\biss\b", r"\birpf?\b", r"\b[pi]is\b", r"\bcofins\b"
    ],
    "consumidor": [
        r"\bprodut[o|a] defeituoso\b", r"\bgarantia\b", r"\bprocon\b", r"\bnegativ[aã]o\b", r"\bcobran[çc]a indevida\b",
        r"\bservi[cç]o\b", r"\bcdc\b"
    ],
    "processual": [
        r"\bpenhora\b", r"\bbloqueio\b", r"\bexecu[cç][aã]o\b", r"\bembargos?\b", r"\bhabeas corpus\b",
        r"\btutela de urg[eê]ncia\b", r"\bagravo\b", r"\bapela[cç][aã]o\b"
    ],
    "criminal": [
        r"\btr[aá]fico\b", r"\bporte de arma\b", r"\bfurto\b", r"\broubo\b", r"\bestelionato\b", r"\blavagem de dinheiro\b"
    ],
}

INTENTS = {
    "duvida_juridica": [
        r"\bcomo\b", r"\bposso\b", r"\btenho direito\b", r"\bo que fazer\b", r"\bpreciso\b", r"\bpergunt[ao]\b",
        r"\bexplicar\b", r"\borienta[cç][aã]o\b", r"\bd[uú]vida\b"
    ],
    "envio_documento": [
        r"\banexo\b", r"\bem anexo\b", r"\bsegue? (o )?documento\b", r"\bsegue? (a )?foto\b", r"\banexei\b"
    ],
    "orçamento_proposta": [
        r"\bquanto custa\b", r"\bpre[çc]o\b", r"\bor[çc]amento\b", r"\bvalores?\b", r"\bhonor[aá]rios?\b",
        r"\bproposta\b", r"\bcontratar\b"
    ],
    "andamento": [
        r"\bandamento\b", r"\bstatus\b", r"\bcomo est[aá]\b", r"\bprogresso\b"
    ],
}

THEMES_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in THEMES.items()}
INTENTS_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in INTENTS.items()}

# ------------------------
# Extração de entidades
# ------------------------
RE_MONEY = re.compile(r"\bR?\$ ?([0-9]{1,3}(\.[0-9]{3})*|[0-9]+)(,[0-9]{2})?\b", re.I)
RE_DATE  = re.compile(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}\-\d{2}\-\d{2})\b")
RE_PROC  = re.compile(r"\b\d{7}\-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
RE_UF    = re.compile(r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b", re.I)
RE_COMARCA = re.compile(r"\b(comarca de|vara|tribunal de|tj\w{1,2})\b.+", re.I)

@dataclass
class EntityPack:
    valores: List[str]
    datas: List[str]
    processos: List[str]
    ufs: List[str]
    jurisdicoes: List[str]
    partes_mencionadas: List[str]
    raw: str

class Classifier:
    """Heurístico leve com fallback opcional para LLM."""
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm

    def classify(self, text: str) -> Tuple[str, str]:
        t = " ".join(text.lower().split())
        intent = "duvida_juridica"
        for key, patterns in INTENTS_COMPILED.items():
            if any(p.search(t) for p in patterns):
                intent = key
                break
        tema = "geral"
        score_max = 0
        best = "geral"
        for key, patterns in THEMES_COMPILED.items():
            hits = sum(1 for p in patterns if p.search(t))
            if hits > score_max:
                score_max = hits
                best = key
        tema = best
        return intent, tema

class Extractor:
    """Extrai entidades comuns do relato do cliente."""
    def extract(self, text: str) -> Dict[str, object]:
        valores = [m.group(0) for m in RE_MONEY.finditer(text)]
        datas = [m.group(0) for m in RE_DATE.finditer(text)]
        processos = [m.group(0) for m in RE_PROC.finditer(text)]
        ufs = list({m.group(0).upper() for m in RE_UF.finditer(text)})
        jurisdicoes: List[str] = []
        for m in RE_COMARCA.finditer(text):
            s = m.group(0).strip()
            if len(s) > 12:
                jurisdicoes.append(s[:200])
        partes: List[str] = []
        for token in re.findall(r"\b[A-ZÁÂÃÉÊÍÓÔÕÚÇ][a-záâãéêíóôõúç]{2,}(?:\s+[A-ZÁÂÃÉÊÍÓÔÕÚÇ][a-záâãéêíóôõúç]{2,}){0,3}\b", text):
            if token.lower() not in {"ex", "art", "tjgo", "stj", "stf"}:
                partes.append(token)
        return {
            "valores": valores[:20],
            "datas": datas[:20],
            "processos": processos[:10],
            "ufs": ufs[:10],
            "jurisdicoes": jurisdicoes[:10],
            "partes_mencionadas": partes[:20],
            "raw": text[:1000],
        }

__all__ = ["AnalisadorDeProblemas", "Classifier", "Extractor", "EntityPack"]