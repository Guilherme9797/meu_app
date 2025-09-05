from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
from ..utils.openai_client import LLM

# --- Ontologia CPC (macro-mapa) ---
_CPC_ONTOLOGY = {
  "direito_processual_civil": {
    "normas_fundamentais_e_principios": {
      "devido_processo_legal": [
        "garantia_de_defesa_e_contraditorio",
        "motivacao_das_decisoes",
        "publicidade_e_sigilo_relativo"
      ],
      "contraditorio_e_ampla_defesa": [
        "ciência_efetiva",
        "direito_de_influencia_e_participacao",
        "producao_de_provas_pelas_partes"
      ],
      "razoavel_duracao_do_processo": [
        "gestao_de_fluxo_e_economia_processual",
        "calendario_processual",
        "saneamento_compartilhado"
      ],
      "boa_fe_processual_e_cooperacao": [
        "deveres_de_lealdade_e_verdade",
        "vedacao_ao_venire_contra_factum_proprium",
        "transparencia_e_colaboracao_com_o_juizo"
      ],
      "adequacao_e_flexibilizacao": [
        "negocios_juridicos_processuais",
        "calibragem_de_ritos_e_prazos",
        "ordem_publica_e_limites"
      ],
      "inafastabilidade_e_acesso_a_justica": [
        "assistencia_judiciaria",
        "gratuidade_de_justica",
        "hipossuficiencia_e_prova"
      ],
      "juizo_natural_e_imparcialidade": [
        "competencia_funcional",
        "distribuicao_e_preventos",
        "impedimentos_e_suspeicao"
      ]
    },

    "competencia_e_organizacao": {
      "competencia_material_e_funcional": [
        "fazenda_publica",
        "infancia_e_juventude",
        "fazendarios_e_regime_proprio",
        "turmas_recursais_juizados"
      ],
      "competencia_territorial": [
        "forum_do_domicilio_do_reu",
        "locais_de_cumprimento_da_obrigacao",
        "competencias_concorrentes_e_eleicao_de_forum"
      ],
      "modificacao_e_prorrogacao": [
        "conexao_e_continencia",
        "prejudicialidade",
        "litispendencia_e_coisa_julgada"
      ],
      "conflitos_de_competencia": [
        "suscitacao",
        "efeitos",
        "competencia_dos_tribunais"
      ]
    },

    "partes_representacao_e_intervencoes": {
      "partes_capacidade_e_representacao": [
        "substituicao_processual",
        "representacao_por_advogado",
        "curadoria_especial"
      ],
      "mp_defensoria_e_amicus_curiae": [
        "intervencao_obrigatoria",
        "amplitude_do_amicus",
        "efeitos_nos_recursos"
      ],
      "litisconsorcio": [
        "facultativo_e_necessario",
        "unitario_e_simples",
        "ulterior_e_multiplo"
      ],
      "intervencoes_de_terceiros": {
        "assistencia": [
          "simples",
          "litisconsorcial"
        ],
        "denunciacao_da_lide": [
          "vicio_evicao",
          "regresso"
        ],
        "chamamento_ao_processo": [
          "devedores_solidarios",
          "fiador_devedor_principal"
        ],
        "incidente_de_desconsideracao_da_pj": [
          "teoria_maior_menor",
          "efeitos_interlocutorios",
          "prova_da_abusividade"
        ],
        "amicus_curiae": [
          "requisitos_representatividade",
          "participacao_na_prova_e_oral",
          "efeitos_no_precedente"
        ]
      }
    },

    "atos_processuais_prazos_e_nulidades": {
      "peticoes_e_requisitos": [
        "peticao_inicial_elementos_essenciais",
        "documentos_indispensaveis",
        "emenda_e_indeferimento"
      ],
      "citacao_intimacao_e_comunicacoes": [
        "modalidades_correio_oficial_cartorio_meio_eletronico",
        "ciencia_inequivoca",
        "nulidade_e_repeticao_de_ato"
      ],
      "prazos": [
        "contagem_em_dias_uteis",
        "suspensao_e_interrupcao",
        "preclusoes_temporal_logica_consumativa"
      ],
      "nulidades_processuais": [
        "teoria_do_prejuizo",
        "convalidacao",
        "ordem_publica_vs_interesse"
      ],
      "processo_eletronico": [
        "protocolos_e_assinaturas",
        "horario_de_corte",
        "juntada_automatica"
      ]
    },

    "tutelas_provisorias": {
      "tutela_de_urgencia": [
        "cautelar",
        "antecipada",
        "probabilidade_do_direito_e_periculum",
        "reversibilidade",
        "contracautela"
      ],
      "tutela_de_evidencia": [
        "hipoteses_legais",
        "provas_documentais_robustas",
        "abuso_do_direito_de_defesa"
      ],
      "estabilizacao_da_antecipada": [
        "ausencia_de_recurso",
        "coisa_julgada_formal_material",
        "revisao_e_rescisao"
      ]
    },

    "procedimento_comum": {
      "fase_postulatoria": [
        "peticao_inicial_causa_de_pedir_e_pedidos",
        "indeferimento_e_emenda",
        "distribuicao_e_justica_gratuita"
      ],
      "contestacao_e_defesas": [
        "preliminares_processuais",
        "merito_diretamente",
        "reconvecao",
        "impugnacao_a_gratuidade",
        "impugnacao_ao_valor_da_causa",
        "excecoes_processuais"
      ],
      "replica_e_saneamento": [
        "impugnacao_as_preliminares",
        "delimitacao_de_fatos",
        "fixacao_dos_pontos_controvertidos",
        "calendario_e_provas"
      ],
      "instrução_e_audiencia": [
        "ordem_da_audiencia",
        "depoimento_pessoal",
        "oitiva_de_testemunhas",
        "pericia_e_seus_esclarecimentos"
      ],
      "julgamento": [
        "sentenca_terminativa_ou_de_merito",
        "julgamento_antecipado_total_parcial",
        "fundamentacao_estruturada"
      ]
    },

    "provas": {
      "distribuicao_dinamica_do_onus": [
        "hipossuficiencia_e_verossimilhanca",
        "tecnica_de_mitigacao_de_dificuldades_probatórias"
      ],
      "documental_e_eletronica": [
        "documento_publico_e_particular",
        "assinatura_eletronica",
        "logs_e_metadata",
        "cadeia_de_custodia_digital"
      ],
      "testemunhal_e_depoimento": [
        "rol_e_substituicao",
        "contraditorio_na_inquiricao",
        "teoria_das_testemunhas_suspeitas"
      ],
      "pericia": [
        "nomeacao_do_perito",
        "quesitos_e_assistentes_tecnicos",
        "laudo_complementar",
        "pericia_contabil_medica_engenharia_ti"
      ],
      "inspecao_judicial": [
        "cabimento",
        "auto_circunstanciado",
        "registro_fotografico_e_video"
      ],
      "producao_antecipada_de_provas": [
        "urgencia_e_justo_receio",
        "prova_autonoma_para_outra_acao"
      ]
    },

    "recursos": {
      "disposicoes_gerais": [
        "efeito_devolutivo_e_suspensivo",
        "fungibilidade",
        "dialeticidade",
        "preparo_e_desercao",
        "honorarios_recursais"
      ],
      "apelacao": [
        "cabimento_hipoteses",
        "efeitos_e_juizo_de_admissibilidade",
        "devolucao_criterios",
        "fato_superveniente_art_1012_par_1"
      ],
      "agravo_de_instrumento": [
        "hipoteses_taxatividade_mitigada",
        "efeito_suspensivo_e_tutela_de_urgencia",
        "agravo_interno"
      ],
      "embargos_de_declaracao": [
        "omissao_contradicao_obscuridade",
        "erro_material",
        "efeitos_infringentes",
        "prazo_interrupcao"
      ],
      "recursos_aos_tribunais_superiores": [
        "recurso_especial_STJ",
        "recurso_extraordinario_STF",
        "repercussao_geral_e_temas",
        "agravo_em_REsp_e_em_RE",
        "juizados_turmas_recursais_e_incidentes_de_uniformizacao"
      ],
      "tecnicas_de_julgamento_colegiado": [
        "ampliacao_do_colegiado_art_942",
        "sustentacao_oral",
        "julgamento_virtual"
      ]
    },

    "precedentes_e_incidentes": {
      "sistema_de_precedentes": [
        "ratio_decidendi",
        "distinguishing_overruling",
        "vinculacao_e_adequacao"
      ],
      "irdr_e_iac": [
        "requisitos_relevancia_e_repetitividade",
        "suspensao_de_processos",
        "efeitos_vinculantes",
        "revisao_e_revogacao"
      ],
      "recursos_repetitivos": [
        "afetação_pelo_STJ_STF",
        "tese_fixada",
        "gestao_de_casos_suspensos"
      ]
    },

    "cumprimento_de_sentenca_e_execucao": {
      "titulos_judiciais": [
        "liquidacao_por_artigos_e_calculos",
        "cumprimento_de_sentenca_por_quantia_certa",
        "astreintes_e_modulacao",
        "impugnacao_ao_cumprimento",
        "cumprimento_contra_a_fazenda_publica_precatorios_RPV"
      ],
      "execucao_de_titulo_extrajudicial": [
        "requisitos_do_titulo",
        "citacao_e_prazo_para_pagamento",
        "penhora_avaliacao_e_expropriacao",
        "adjudicacao_alienacao_praca",
        "embargos_a_execucao",
        "excecao_de_pre_executividade"
      ],
      "meios_atipicos_de_execucao": [
        "medidas_indutivas_coercitivas",
        "sisbajud_renajud_infojud",
        "suspensao_e_extincao"
      ],
      "defesas_e_incidentes": [
        "embargos_de_terceiro",
        "fraude_a_execucao",
        "fraude_contra_credores",
        "impugnacao_ao_calculo",
        "excesso_de_execucao"
      ]
    },

    "procedimentos_especiais": {
      "monitoria": [
        "prova_escrita_sem_eficacia_de_titulo",
        "mandado_monitorio",
        "constituicao_de_titulo"
      ],
      "possessorias": [
        "manutencao_reintegracao_interdito_proibitorio",
        "forca_nova_e_forca_velha",
        "liminar_e_audiencia_de_justificacao"
      ],
      "inventario_e_partilha": [
        "arrolamento_simplificado",
        "inventario_extrajudicial",
        "colacao_e_sonegacao",
        "sobrepartilha"
      ],
      "alimentos": [
        "provisorios_e_definitivos",
        "cumprimento_com_prisao_civil",
        "desconto_em_folha"
      ],
      "interdicao_e_tomada_de_decisao_apoiada": [
        "curatela_proporcionalidade",
        "provas_medicas",
        "limites_de_atuacao"
      ],
      "consignacao_em_pagamento": [
        "depósito_judicial",
        "liberacao_do_devedor",
        "resistencia_do_credor"
      ],
      "producao_antecipada_de_prova": [
        "autonomia",
        "contraditorio_mitigado",
        "vinculo_com_acao_principal"
      ],
      "restauracao_de_autos": [
        "perda_dos_autos",
        "reconstrucao_por_copias",
        "homologacao"
      ]
    },

    "fazenda_publica_e_coletivos": {
      "fazenda_publica_em_juizo": [
        "prazos_em_dobro",
        "remessa_necessaria",
        "bloqueios_sisbajud_limites",
        "cumprimento_contra_fazenda_precatorio_rpv"
      ],
      "acoes_coletivas_e_tutela_dos_direitos_transindividuais": [
        "acao_civil_publica",
        "mandado_de_seguranca_coletivo",
        "legitimidade_ativa_coletiva",
        "coisa_julgada_erga_omnes"
      ]
    },

    "justica_multiportas_e_autocomposicao": {
      "conciliacao_e_mediacao": [
        "centros_judiciarios_Cejusc",
        "audiencia_pre-processual",
        "titulacao_do_acordo"
      ],
      "negociacao_processual": [
        "ajustes_de_prazo_e_prova",
        "calendario_e_organizacao"

      ]
    }
  }
}

def _norm_txt(s: str) -> str:
    """minúsculas, sem acento, troca '_' por espaço"""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().replace("_", " ").strip()

def _iter_ontology_paths(node, prefix=""):
    """Gera (path, label_normalizada) para cada chave/folha."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{prefix}.{k}" if prefix else k
            out.append((p, _norm_txt(k)))
            out.extend(_iter_ontology_paths(v, p))
    elif isinstance(node, list):
        for item in node:
            p = f"{prefix}.{item}" if prefix else item
            out.append((p, _norm_txt(item)))
    else:
        if prefix:
            out.append((prefix, _norm_txt(prefix.split(".")[-1])))
    return out

def _get_node_by_path(node, path: str):
    parts = path.split(".")
    cur = node
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur

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