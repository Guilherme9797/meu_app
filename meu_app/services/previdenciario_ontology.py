"""Ontologia de Direito Previdenciário para detecção temática."""

_PREVID_ONTOLOGY = {
  "direito_previdenciario": {
    "seguridade_social": {
      "conceitos_e_fundamentos": [
        "seguridade_social_saude_previdencia_assistencia",
        "principio_da_solidariedade",
        "universalidade_da_cobertura",
        "equidade_no_custeio",
        "diversidade_da_base_de_financiamento"
      ],
      "organizacao": [
        "rgps_regime_geral",
        "rpps_regimes_proprios",
        "militares",
        "regimes_complementares"
      ],
      "custeio": [
        "contribuicoes_dos_empregados",
        "contribuicoes_dos_empregadores",
        "contribuicoes_de_autonomos",
        "contribuicoes_de_microempreendedores_mei",
        "contribuicoes_de_entidades_economicas",
        "ctc_certidao_de_tempo_de_contribuicao"
      ]
    },

    "segurados": {
      "obrigatorios": [
        "empregado",
        "empregado_domestico",
        "contribuinte_individual",
        "avulso",
        "segurado_especial_rural"
      ],
      "facultativos": [
        "estudantes",
        "donas_de_casa",
        "brasileiros_no_exterior"
      ],
      "qualidade_de_segurado": [
        "manutencao_do_vinculo",
        "periodo_de_graca",
        "perda_da_qualidade",
        "recuperacao_da_qualidade"
      ],
      "dependentes": [
        "classe_i_conjuge_companheiro_filhos",
        "classe_ii_pais",
        "classe_iii_irmaos"
      ]
    },

    "carencia_e_tempo_de_contribuicao": {
      "carencia": [
        "conceito",
        "dispensa_em_acidentes",
        "dispensa_em_beneficios_especificos"
      ],
      "tempo_de_contribuicao": [
        "ctps",
        "cnis",
        "tempo_rural",
        "tempo_especial_ppp_lcat_epi",
        "contagem_recíproca"
      ]
    },

    "beneficios_do_rgps": {
      "aposentadorias": {
        "aposentadoria_por_idade": [
          "requisitos_idade_minima",
          "carencia",
          "regra_de_transicao"
        ],
        "aposentadoria_por_tempo_de_contribuicao": [
          "pedagio",
          "fator_previdenciario",
          "regra_85_95_progressiva"
        ],
        "aposentadoria_especial": [
          "exposicao_a_agentes_nocivos",
          "tempo_de_atividade_especial",
          "ppp_perfil_profissiografico",
          "lcat_laudo_tecnico"
        ],
        "aposentadoria_por_invalidez": [
          "incapacidade_total_permanente",
          "conversao_de_auxilio_doenca",
          "carencia"
        ]
      },
      "pensao_por_morte": [
        "qualidade_de_dependente",
        "duracao_por_idade",
        "acumulacao_com_outros_beneficios"
      ],
      "auxilios": [
        "auxilio_doenca_incapacidade_temporaria",
        "auxilio_acidente_reducao_da_capacidade",
        "auxilio_reclusao"
      ],
      "salario_maternidade": [
        "requisitos_carencia",
        "duracao",
        "segurada_especial"
      ],
      "salario_familia": [
        "requisitos",
        "valor",
        "extincao"
      ]
    },

    "beneficios_do_rpps": {
      "aposentadorias": [
        "voluntaria_idade",
        "voluntaria_tempo_contribuicao",
        "invalidez",
        "compulsoria"
      ],
      "pensoes": [
        "dependentes",
        "regras_de_transicao"
      ]
    },

    "acumulacao_de_beneficios": {
      "vedacoes": [
        "duas_aposentadorias_no_rgps",
        "aposentadoria_com_auxilio_doenca",
        "pensao_por_morte_com_pensao_por_morte"
      ],
      "permitidas": [
        "aposentadoria_rgps_com_pensao_rpps",
        "pensao_por_morte_com_aposentadoria"
      ]
    },

    "revisoes_e_temas_repetitivos": {
      "revisao_da_vida_toda": [
        "inclusao_de_salarios_anteriores_a_94",
        "posicionamento_do_stf_e_stj"
      ],
      "revisao_do_teto": [
        "emendas_constitucionais",
        "efeitos_financeiros"
      ],
      "revisao_de_beneficio": [
        "erro_de_calculo",
        "indice_de_correcao",
        "revisao_de_fato_novo"
      ],
      "desaposentacao": [
        "conceito",
        "jurisprudencia_do_stf",
        "impossibilidade",
        "reaposentacao"
      ]
    },

    "processo_previdenciario": {
      "fase_administrativa": [
        "requerimento_no_inss",
        "pericia_medica",
        "indeferimento_e_recurso_administrativo"
      ],
      "fase_judicial": [
        "justica_federal",
        "juizados_especiais_federais",
        "tutelas_de_urgencia_em_beneficios",
        "prova_pericial_medica_e_tecnica"
      ]
    }
  }
}