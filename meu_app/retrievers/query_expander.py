# -*- coding: utf-8 -*-
from __future__ import annotations
import unicodedata, re
from typing import List, Set

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()

def _ngrams(tokens: List[str], n: int = 2) -> List[str]:
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

_ALIASES = {
    "negativacao": ["serasa", "spc", "inscricao indevida", "nome sujo"],
    "injuria": ["injuria", "injúria", "ofensa", "xingamento"],
    "calunia": ["calunia", "calúnia", "acusacao falsa"],
    "difamacao": ["difamacao", "difamação", "exposicao indevida"],
    "transferencia veiculo": ["transferencia de veiculo", "crlv", "dut", "multa apos venda"],
    "acidente de transito": ["colisao", "batida de carro", "sinistro", "dpvat"],
    "compra e venda imovel": ["escritura", "promessa de compra e venda", "matricula", "registro"],
}

def _expand_synonyms(text: str) -> List[str]:
    t = _norm(text)
    out: Set[str] = set()
    for head, alts in _ALIASES.items():
        for a in alts + [head]:
            if a in t:
                out.add(head)
                out.update(alts)
    return list(out)

def _basic_variants(text: str) -> List[str]:
    t = _norm(text)
    tokens = re.findall(r"[a-z0-9]+", t)
    out: Set[str] = set()
    out.update(_ngrams(tokens, 2))
    out.update(_ngrams(tokens, 3))
    out.update([
        t.replace("transferencia","transferir"),
        t.replace("vendeu","venda"),
        t.replace("bateram","batida"),
        t.replace("divida","débito"),
        t.replace("caloteiro","inadimplente"),
    ])
    return [x for x in out if x and len(x) > 3]

def expand(user_text: str, max_items: int = 6) -> List[str]:
    syns = _expand_synonyms(user_text)
    vars_ = _basic_variants(user_text)
    base = [_norm(user_text)]
    allq = []
    seen = set()
    for q in base + syns + vars_:
        if q and q not in seen:
            seen.add(q)
            allq.append(q)
        if len(allq) >= max_items:
            break
    return allq