from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Iterable, Tuple
import re
import unicodedata
import json
import os

# ========= Normalização =========

def _norm(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s


def _labelize(s: str) -> str:
    """snake_case -> 'snake case' (sem acentos; casado com _norm)"""
    return _norm(s.replace("/", " ").replace("\\", " ").replace("-", " ").replace("_", " "))


def _variants(token: str) -> List[str]:
    """
    Gera variações simples para disparo:
    - snake, com espaços, sem separador.
    """
    t = token.strip()
    if not t:
        return []
    v = set()
    v.add(t)
    v.add(t.replace("_", " "))
    v.add(t.replace("_", ""))
    return list(v)


# ========= Pattern Rules =========


@dataclass
class PatternRule:
    name: str
    any_of: List[str]
    none_of: List[str] = field(default_factory=list)
    dominios: List[str] = field(default_factory=list)
    institutes: List[str] = field(default_factory=list)
    bens: List[str] = field(default_factory=list)
    atos: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


# ========= Mapeamento de domínios (chave de topo -> domínios amplos do orquestrador) =========

_TOP_TO_DOMAIN = {
    # substantivos
    "direito_civil": ["civil"],
    "direito_processual_civil": ["processual_civil"],
    "direito_penal": ["penal"],
    "direito_penal_parte_geral": ["penal"],
    "direito_penal_parte_especial": ["penal"],
    "direito_processual_penal": ["processual_penal"],
    "direito_tributario": ["tributário"],
    "direito_empresarial": ["empresarial"],
    "direito_previdenciario": ["previdenciário"],
    "direito_administrativo": ["administrativo"],
    "direito_ambiental": ["ambiental"],
    "direito_do_consumidor": ["consumidor"],
    "direito_imobiliario": ["imobiliário", "civil"],
    "direito_do_trabalho": ["trabalho"],
    "direito_processual_do_trabalho": ["processual_trabalho"],
    "direito_de_familia": ["família"],
    "direito_das_sucessoes": ["sucessões"],
    # variações possíveis que possam aparecer
    "civil": ["civil"],
    "processual_civil": ["processual_civil"],
    "penal": ["penal"],
    "processual_penal": ["processual_penal"],
    "tributario": ["tributário"],
    "empresarial": ["empresarial"],
    "previdenciario": ["previdenciário"],
    "administrativo": ["administrativo"],
    "ambiental": ["ambiental"],
    "consumidor": ["consumidor"],
    "imobiliario": ["imobiliário", "civil"],
    "trabalho": ["trabalho"],
    "processual_trabalho": ["processual_trabalho"],
    "familia": ["família"],
    "sucessoes": ["sucessões"],
}


def _dominios_for_topkey(k: str) -> List[str]:
    k = _norm(k).replace(" ", "_")
    return _TOP_TO_DOMAIN.get(k, [])


# ========= Compilador: Taxonomia (dict/list) -> Lista[PatternRule] =========


def _iter_taxonomy(tree: Any, path: List[str]) -> Iterable[Tuple[List[str], str | None]]:
    """
    Itera nós da taxonomia. Para cada folha (string) em uma lista, retorna (path, leaf).
    Para dicionários intermediários, desce recursivamente.
    """
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from _iter_taxonomy(v, path + [k])
    elif isinstance(tree, list):
        for leaf in tree:
            if isinstance(leaf, str):
                yield (path, leaf)
            else:
                # listas aninhadas incomuns: tentar descer
                yield from _iter_taxonomy(leaf, path)
    elif isinstance(tree, str):
        yield (path, tree)
    # outros tipos são ignorados


def rules_from_taxonomy(tax: Dict[str, Any]) -> List[PatternRule]:
    """
    Converte a ÁRVORE gigante que você colou (civil, penal, consumidor, etc.)
    em centenas/milhares de PatternRule sem hardcode.
    - name: caminho “topo/sub/.../folha”
    - any_of: variações do caminho e da folha
    - dominios: mapeados a partir da chave de topo
    - institutes: rótulos do caminho útil + folha (em linguagem natural simples, sem acentos)
    """
    rules: List[PatternRule] = []
    if not isinstance(tax, dict):
        return rules

    for top, subtree in tax.items():
        dominios = _dominios_for_topkey(top) or []
        top_lbl = _labelize(top)

        for path, leaf in _iter_taxonomy(subtree, [top]):
            # labels/gatilhos
            labels: List[str] = []
            for seg in path[1:]:  # pula o topo (já está em dominios)
                labels.append(_labelize(seg))
            leaf_lbl = _labelize(leaf) if leaf is not None else None

            # any_of inclui: cada segmento, o caminho unido e a folha
            triggers: Set[str] = set()
            path_tokens = [seg.replace(" ", "_") for seg in labels]
            if leaf_lbl:
                triggers.update(_variants(leaf_lbl.replace(" ", "_")))
            # também dispare por segmentos e pelo caminho todo
            for seg in path_tokens:
                triggers.update(_variants(seg))
            if path_tokens:
                triggers.update(_variants("_".join(path_tokens)))

            # institutes: usar as partes “legíveis”
            institutes: List[str] = []
            if labels:
                institutes.extend(labels)
            if leaf_lbl:
                institutes.append(leaf_lbl)

            name = "/".join([_labelize(p) for p in path] + ([leaf_lbl] if leaf_lbl else [])) or top_lbl

            # Heurísticas leves de bens/atos, sem amarrar a casos específicos
            bens: List[str] = []
            atos: List[str] = []
            path_join = " ".join(labels + ([leaf_lbl] if leaf_lbl else []))
            if any(x in path_join for x in ["imovel", "imobiliario", "condominio", "usucapiao", "matricula", "registro"]):
                bens.append("imóvel")
            if any(x in path_join for x in ["veiculo", "ipva", "detran"]):
                bens.append("veículo")
            if "adjudicacao" in path_join:
                atos.append("ajuizar adjudicação compulsória")
            if any(x in path_join for x in ["obrigacao de fazer", "registro", "transferencia", "outorga"]):
                atos.append("obrigação de fazer (cumprimento específico)")

            rule = PatternRule(
                name=name,
                any_of=sorted(triggers),
                dominios=sorted(set(dominios)),
                institutes=sorted(set(institutes)),
                bens=sorted(set(bens)),
                atos=sorted(set(atos)),
                keywords=[],
            )
            # evitar regras vazias de gatilho
            if rule.any_of:
                rules.append(rule)

    return rules


# ========= Loader robusto de arquivos com VÁRIOS JSONs colados =========


def _load_many_json(path: str) -> Dict[str, Any]:
    """
    Aceita:
    - Um único JSON-objeto (dict grande)
    - Vários objetos JSON colados em sequência (serão mesclados no mesmo dict)
    """
    with open(path, "r", encoding="utf-8") as f:
        s = f.read().strip()
    # Tenta parse direto
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Parser incremental
    decoder = json.JSONDecoder()
    idx = 0
    merged: Dict[str, Any] = {}
    while idx < len(s):
        s = s[idx:].lstrip()
        if not s:
            break
        try:
            obj, end = decoder.raw_decode(s)
        except Exception:
            break
        if isinstance(obj, dict):
            # mescla chaves de topo
            for k, v in obj.items():
                if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                    # merge rasa
                    merged[k].update(v)
                else:
                    merged[k] = v
        idx = end
    return merged



def load_rules_from_taxonomy_path(path: str) -> List[PatternRule]:
    if not path or not os.path.exists(path):
        return []
    try:
        tax = _load_many_json(path)
        return rules_from_taxonomy(tax)
    except Exception:
        return []


# ========= Loader “antigo” (lista direta de PatternRule em JSON) =========


def load_rules_from_json(path: str) -> List[PatternRule]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    rules: List[PatternRule] = []
    for r in raw:
        rules.append(PatternRule(**r))
    return rules


# ========= Regras base (poucas, amplas) + Taxonomia externa (ENORME) =========

BASE_RULES: List[PatternRule] = [
    # Alguns “coringas” úteis; o grosso virá da taxonomia carregada
    PatternRule(
        name="inadimplemento_contratual",
        any_of=["inadimplemento", "descumprimento", "multa_contratual", "quebrou_contrato"],
        dominios=["civil", "processual_civil"],
        institutes=["responsabilidade contratual", "resolução contratual", "cumprimento específico"],
        atos=["notificar extrajudicialmente", "ajuizar obrigação de fazer ou pagar"],
        keywords=["cpc 497", "cpc 536"],
    ),
    PatternRule(
        name="danos_materiais_e_morais",
        any_of=["dano_moral", "dano_material", "indenizacao", "lucros_cessantes"],
        dominios=["civil", "consumidor", "trabalho"],
        institutes=["responsabilidade civil"],
        atos=["quantificar danos", "ajuizar indenização"],
        keywords=[],
    ),
]

# Carrega automáticamente a mega-taxonomia se houver
EXTERNAL_TAX_PATH = os.getenv("MEU_APP_TAXONOMIA_EXTENSA", "").strip()
EXTRA_RULES: List[PatternRule] = load_rules_from_taxonomy_path(EXTERNAL_TAX_PATH) if EXTERNAL_TAX_PATH else []

# DEFAULT_RULES expostas ao motor
DEFAULT_RULES: List[PatternRule] = BASE_RULES + EXTRA_RULES


# ========= Motor de aplicação =========


def apply_patterns(text: str, extra_rules: List[PatternRule] | None = None) -> Dict[str, List[str]]:
    """
    Recebe o texto do usuário e devolve um “frame bruto” (domínios, institutos, bens, atos, keywords).
    Combina DEFAULT_RULES com extra_rules (se houver).
    """
    p = _norm(text)
    rules = DEFAULT_RULES + (extra_rules or [])

    dom: Set[str] = set()
    inst: Set[str] = set()
    bens: Set[str] = set()
    atos: Set[str] = set()
    kw: Set[str] = set()

    for rule in rules:
        # Disparo se QUALQUER trigger estiver presente (após normalização)
        if any(_norm(tok) in p for tok in rule.any_of) and not any(
            _norm(tok) in p for tok in rule.none_of
        ):
            dom.update(rule.dominios)
            inst.update(rule.institutes)
            bens.update(rule.bens)
            atos.update(rule.atos)
            kw.update(rule.keywords)

    return {
        "dominios": sorted(dom),
        "institutos": sorted(inst),
        "bens_relacionados": sorted(bens),
        "atos_centrais": sorted(atos),
        "palavras_chave": sorted(kw),
    }