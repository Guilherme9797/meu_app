from __future__ import annotations
import json as _json

_PENAL_ONTOLOGY = _json.loads(
    '''
{
  "direito_penal": {
    "parte_geral": {
      "fundamentos": [
        "funcao_do_direito_penal",
        "princípios_da_legalidade_e_anterioridade",
        "princípio_da_intervenção_mínima",
        "princípio_da_ofensividade",
        "princípio_da_proporcionalidade",
        "princípio_da_humanidade_da_pena",
        "princípio_da_insignificancia"
      ],
      "fontes_e_interpretacao": [
ååååååååååååååååååååååååååååååååååååååååååååååååume",
        "fonte_formal_constituicao_código_leis_penais_extravagantes",
        "interpretacao_literal_extensiva_restritiva",
        "interpretacao_analogica_in_malampartem_in_bonampartem",
        "leis_penais_em_branco",
        "lei_penal_no_tempo_irretroatividade_retroatividade_benefica",
        "lei_penal_no_espaco_territorialidade_extraterritorialidade"
      ],
      "teoria_do_crime": {
        "fato_tipico": [
          "conduta_comissiva_omissiva",
          "resultado_material_formal",
          "nexo_causal_teoria_da_equivalencia_dos_antecedentes",
          "tipicidade_formal_e_material",
          "tipicidade_conglobante"
        ],
        "ilicitude": [
          "estado_de_necessidade",
          "legitima_defesa",
          "estrito_cumprimento_do_dever_legal",
          "exercicio_regular_de_direito",
          "excludentes_supralegais",
          "ilicitude_principio_da_proporcionalidade"
        ],
        "culpabilidade": [
          "imputabilidade_penal_maioridade_doenca_mental_embriaguez",
          "potencial_consciencia_da_ilicitude",
          "exigibilidade_de_conduta_diversa",
          "erro_de_proibicao_inevitavel_e_evitavel"
        ],
        "iter_criminis": [
          "cogitação",
          "atos_preparatorios",
          "execucao",
          "consumacao",
          "tentativa",
          "desistencia_voluntaria",
          "arrependimento_eficaz",
          "arrependimento_posterior",
          "crime_impossivel"
        ],
        "elemento_subjetivo": [
          "dolo_direto_eventual",
          "culpa_consciente_inconsciente",
          "preterdolo"
        ]
      },
      "concurso_de_pessoas": [
        "coautoria_participacao",
        "autor_imediato_e_mediato",
        "instigacao_e_induzimento",
        "dominio_do_fato",
        "responsabilidade_por_excesso"
      ],
      "concurso_de_crimes": [
        "concurso_material",
        "concurso_formal_proprio_improprio",
        "crime_continuado",
        "consuncao_absorcao",
        "especialidade",
        "subsidiariedade"
      ],
      "penas": {
        "tipos": [
          "privativas_de_liberdade",
          "restritivas_de_direitos",
          "multa"
        ],
        "dosimetria": [
          "sistema_trifasico",
          "circunstancias_judiciais_art_59",
          "atenuantes_e_agravantes",
          "causas_de_aumento_e_diminuicao"
        ],
        "substituicao_e_sursis": [
          "substituicao_por_restritivas",
          "sursis_penal",
          "regime_inicial_de_cumprimento"
        ],
        "medidas_de_seguranca": [
          "internacao",
          "tratamento_ambulatorial",
          "prazo_minimo",
          "periculosidade"
        ]
      },
      "extincao_da_punibilidade": [
        "morte_do_agente",
        "anistia_graca_indulto",
        "prescricao_da_pretensao_punitiva",
        "prescricao_da_pretensao_executoria",
        "decadencia",
        "perempcao",
        "renuncia_e_perdao_do_ofendido"
      ]
    },

    "parte_especial": {
      "crimes_contra_a_pessoa": {
        "vida": [
          "homicidio_simples",
          "homicidio_qualificado",
          "homicidio_privilegiado",
          "feminicidio",
          "infanticidio",
          "aborto_provocado_pela_gestante",
          "aborto_provocado_por_terceiro",
          "aborto_sentimental_e_terapeutico",
          "crime_de_inducao_ao_aborto"
        ],
        "integridade_corporal": [
          "lesao_corporal_leve",
          "lesao_corporal_grave",
          "lesao_corporal_gravissima",
          "lesao_culposa",
          "lesao_domestica_violencia_maria_da_penha",
          "lesao_seguida_de_morte"
        ],
        "honra": [
          "calunia",
          "difamacao",
          "injuria",
          "injuria_racial_lei_14532_2023",
          "injuria_coletiva"
        ],
        "liberdade": [
          "ameaca",
          "constrangimento_ilegal",
          "sequestro_carcere_privado",
          "reducao_a_condicao_analogica_a_escravo",
          "violacao_de_domicilio"
        ],
        "dignidade_sexual": [
          "estupro",
          "estupro_de_vulneravel",
          "violacao_sexual_mediante_fraude",
          "ato_obsceno",
          "importunacao_sexual",
          "assédio_sexual",
          "mediação_para_exploração_sexual",
          "favorecimento_prostituicao"
        ]
      },
      "crimes_contra_o_patrimonio": [
        "furto_simples",
        "furto_qualificado",
        "roubo_simples",
        "roubo_majorado",
        "extorsao",
        "sequestro_relampago",
        "estelionato",
        "apropiacao_indebita",
        "receptacao",
        "dano_simples_e_qualificado",
        "usurpacao",
        "esbulho_possessório"
      ],
      "crimes_contra_a_fe_publica": [
        "moeda_falsa",
        "falsificacao_documento_publico",
        "falsificacao_documento_particular",
        "uso_de_documento_falso",
        "falsidade_ideologica",
        "falsificacao_de_selo_ou_sinal_publico"
      ],
      "crimes_contra_a_administracao_publica": [
        "peculato",
        "peculato_furto",
        "peculato_desvio",
        "concussao",
        "corrupcao_passiva",
        "corrupcao_ativa",
        "prevaricacao",
        "resistencia",
        "desobediencia",
        "desacato",
        "advocacia_administrativa",
        "contrabando_e_descaminho"
      ],
      "crimes_contra_a_paz_publica": [
        "associacao_criminosa",
        "organizacao_criminosa_lei_12850_2013",
        "apologia_de_crime_ou_criminoso",
        "incitacao_ao_crime"
      ],
      "crimes_em_legislacoes_extravagantes": {
        "lei_de_drogas": [
          "trafico_de_drogas",
          "associacao_para_o_trafico",
          "financiamento_do_trafico",
          "porte_para_consumo_pessoal",
          "tráfico_privilegiado_art_33_par_4"
        ],
        "estatuto_do_desarmamento": [
          "porte_ilegal_de_arma",
          "posse_ilegal_de_arma",
          "comercio_ilegal_de_arma",
          "trafico_internacional_de_armas"
        ],
        "lei_de_crimes_ambientais": [
          "poluicao",
          "crime_contra_fauna",
          "crime_contra_flora",
          "crime_contra_patrimonio_cultural"
        ],
        "crimes_de_transito": [
          "homicidio_culposo_no_transito",
          "lesao_culposa_no_transito",
          "embriaguez_ao_volante",
          "fuga_do_local_de_acidente"
        ],
        "lei_de_licitacoes": [
          "fraude_a_licitacao",
          "contratacao_direta_irregular",
          "sobrepreço_superfaturamento"
        ]
      }
    }
  }
}
''')