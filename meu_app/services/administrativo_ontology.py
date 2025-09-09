from __future__ import annotations

"""Ontologia de Direito Administrativo para detecção temática."""

_ADMINISTRATIVO_ONTOLOGY = {
  "direito_administrativo": {
    "principios_e_fontes": {
      "principios_constitucionais": [
        "legalidade",
        "impessoalidade",
        "moralidade",
        "publicidade",
        "eficiencia",
        "supremacia_do_interesse_publico",
        "indisponibilidade_do_interesse_publico",
        "proporcionalidade_razoabilidade",
        "motivacao",
        "seguranca_juridica_confiança_legitima",
        "autotutela",
        "continuidade_do_servico_publico"
      ],
      "fontes": [
        "constitucionais",
        "leis_ordinarias_e_complementares",
        "decretos_regulamentos",
        "jurisprudencia",
        "costumes_e_principios_gerais",
        "contratos_e_atos_normativos_internos"
      ]
    },

    "organizacao_administrativa": {
      "entidades": [
        "administracao_direta",
        "autarquias",
        "fundacoes_publicas",
        "empresas_publicas",
        "sociedades_de_economia_mista",
        "consorcios_publicos"
      ],
      "descentralizacao_e_desconcentracao": [
        "outorga",
        "delegacao",
        "agencias_executivas",
        "orgaos_e_competencias"
      ],
      "agencias_reguladoras": [
        "natureza_juridica",
        "autonomia",
        "poder_normativo_sancionador",
        "contrato_de_gestao",
        "controle_judicial"
      ]
    },

    "atos_administrativos": {
      "conceito_elementos": [
        "competencia", "finalidade", "forma", "motivo", "objeto"
      ],
      "atributos": [
        "presuncao_de_legalidade_e_veracidade",
        "imperatividade", "autoexecutoriedade", "tipicidade"
      ],
      "classificacao": [
        "vinculados_e_discricionarios",
        "gerais_e_individuais",
        "simples_complexos_e_compostos"
      ],
      "valide_e_invalidade": [
        "nulidade_e_anulabilidade",
        "convalidacao",
        "revogacao_por_oportunidade_e_conveniencia",
        "cassacao_e_conversao"
      ],
      "controle_e_motivacao": [
        "motivacao_explicita",
        "teoria_dos_motivos_determinantes",
        "desvio_de_finalidade",
        "excesso_de_poder"
      ]
    },

    "poderes_administrativos": {
      "poder_hierarquico": ["ordenacao_e_fiscalizacao","delegacao_e_avocacao"],
      "poder_disciplinar": ["sanção_a_servidores_e_particulares","pad_e_devido_processo"],
      "poder_regulamentar": ["decretos_autonomos_e_de_execucao","instrucoes_normativas"],
      "poder_de_policia": [
        "autoexecutoriedade","coercibilidade","ciclo_de_policia_ordine",
        "limites_constitucionais","responsabilidade_por_excesso"
      ]
    },

    "agentes_publicos_e_servidores": {
      "categorias": [
        "agentes_politicos","servidores_estatutarios","empregados_publicos_celetistas",
        "temporarios","delegatarios"
      ],
      "ingresso_e_concurso_publico": [
        "edital_e_vinculacao","direito_a_nomeacao_aprovado_dentro_das_vagas",
        "pretericao_e_candidatos_reservas","cotase_inclusao",
        "exames_psicologicos_e_testes_fisicos"
      ],
      "regime_juridico": [
        "estabilidade","estagio_probatorio","acumulacao_de_cargos",
        "ferias_licencas_adicionalidades","remuneracao_subsidio_teto"
      ],
      "responsabilidade_dos_agentes": ["civil","administrativa","penal"]
    },

    "processo_administrativo_disciplinar_PAD": {
      "principios_e_garantias": [
        "contraditorio_e_ampla_defesa","devido_processo_legal",
        "motivacao_da_decisao","proporcionalidade_da_sancao"
      ],
      "fase_preliminar": ["sindicancia","instauracao_por_portaria","afastamento_preventivo"],
      "instrucao": ["citacao_e_defesa_previa","producao_de_provas","relatorio_da_comissao"],
      "julgamento_e_recursos": ["autoridade_competente","reconsideracao_e_recursos_hierarquicos","revisao_do_pad"],
      "sancoes": ["advertencia","suspensao","demissao","cassacao_de_aposentadoria","destituicao_de_cargo_em_comissao"]
    },

    "servicos_publicos": {
      "conceito_e_principios": ["continuidade","generalidade","modicidade_tarifaria","eficiencia","transparencia"],
      "formas_de_prestacao": ["centralizada","delegada_concessao_permissao_autorizacao","parcerias_publico_privadas_ppp"],
      "regulacao_e_fiscalizacao": ["contratos_e_metas","agencias_reguladoras","ouvidorias_e_participacao_social"],
      "tarifas_e_precos_publicos": ["natureza_juridica","reajuste_e_revisao","equilibrio_economico_financeiro"]
    },

    "licitacoes_e_contratos": {
      "lei_14133_2021_estrutura": [
        "planejamento_pnae_estudos_tecnicos","matriz_de_risco","instrumentos_convocatorios",
        "modos_de_disputa_aberto_fechado",
        "criterios_de_julgamento_menor_preco_tecnica_e_preco_maior_desconto",
        "fase_recursal_unica"
      ],
      "modalidades_e_procedimentos": [
        "concorrencia","concurso","leilao","pregao_para_bens_e_servicos_comuns","dialogo_competitivo"
      ],
      "contratacao_direta": [
        "dispensa_de_licitacao_hipoteses","inexigibilidade_inviabilidade_de_competicao","credenciamento_e_chamamento_publico"
      ],
      "contratos_administrativos": [
        "clausulas_exorbitantes","alteracao_unilateral","fiscalizacao_e_gestao_contratual",
        "equilibrio_economico_financeiro_recomposicao","garantias","sanções_e_penalidades"
      ],
      "impugnacoes_e_controle": ["impugnacao_do_edital","representacao_ao_tribunal_de_contas","controle_judicial"]
    },

    "parcerias_setor_privado": {
      "ppp_e_concessoes": [
        "concessao_comum","concessao_patrocinada","concessao_administrativa",
        "equilibrio_economico_financeiro","matriz_de_riscos","step_in_rights",
        "encampacao_caducidade","prorrogacao_e_relicitacao"
      ],
      "terceiro_setor": ["os_oscip_ongs","termos_de_fomento_e_colaboracao","acordos_de_cooperacao","prestacao_de_contas_e_sancoes"],
      "convenios_e_ajustes": ["instrumentos_entre_entes_publicos","transferencias_voluntarias","plano_de_trabalho_e_objetos"]
    },

    "responsabilidade_civil_do_estado": {
      "regra_geral": [
        "responsabilidade_objetiva_teoria_do_risco_administrativo",
        "omissao_estatal_e_responsabilidade_subjetiva",
        "fato_de_terceiro_e_caso_fortuito","regresso_contra_agente_com_dolo_ou_culpa"
      ],
      "danos_e_reparacao": [
        "dano_material_e_moral","lucros_cessantes","pessoas_privadas_em_estabelecimentos_penais",
        "acidentes_em_servicos_publicos","saude_e_medicamentos"
      ],
      "responsabilidade_por_licenciamento_e_obra_publica": [
        "desapropriacao_indireta","ocupacao_temporaria","restricao_de_acesso_e_lucro_cessante"
      ]
    },

    "intervencao_na_propriedade_e_bens_publicos": {
      "intervencao": [
        "desapropriacao_por_utilidade_publica","desapropriacao_por_interesse_social",
        "servidao_administrativa","requisicao_administrativa","tombamento","limitações_administrativas"
      ],
      "bens_publicos": [
        "classificacao_de_uso_comum_especial_dominicais","afectacao_e_desafectacao",
        "concessao_de_direito_real_de_uso","permicao_de_uso_autorizacao_de_uso","alienacao_e_doacao_com_encargo"
      ]
    },

    "processo_administrativo_lei_9784_99": {
      "principios": ["oficialidade","informalismo_em_favor_do_administrado","verdade_material","motivacao","seguranca_juridica_confiança"],
      "faseamento": ["iniciacao_de_oficio_ou_a_pedido","instrução_probatória","decisao","recursos_e_revisao","prazo_razoavel_e_preclusao_adm"],
      "participacao_e_transparencia": ["vista_e_copia_dos_autos","intimacoes","audiencias_e_consultas_publicas"]
    },

    "improbidade_administrativa": {
      "lei_8429_com_redacao_atual": [
        "atos_tipificados_enriquecimento_ilicito","atos_que_causam_prejuizo_ao_erario",
        "atos_contra_principios_da_administracao","exigencia_de_dolo_para_alguns_tipos","culpa_grave_em_hipoteses_restritas"
      ],
      "sancoes_e_efeitos": [
        "perda_dos_bens","ressarcimento_ao_erario","suspensao_dos_direitos_politicos",
        "multa_civil","proibicao_de_contratar_e_receber_beneficios","dosimetria_e_proporcionalidade"
      ],
      "processual": [
        "legitimidade_ativa_mp_e_pessoa_juridica_interessada","acordo_de_nao_persecucao_civel_compatibilidades",
        "prescricao_e_marcos_interrupcao","cooperacao_premiada_civel"
      ]
    },

    "controle_da_administracao_publica": {
      "controle_interno_e_externo": [
        "orgaos_de_controle_interno","tribunais_de_contas_competencias",
        "controle_legislativo","controle_judicial_ato_vinculado_e_discricionario"
      ],
      "acoes_constitucionais": [
        "mandado_de_seguranca_individual_coletivo","mandado_de_injuncao",
        "acao_popular","acao_civil_publica","habeas_data"
      ],
      "lei_de_acesso_a_informacao_LAI": [
        "transparencia_ativa_e_passiva","sigilos_e_protecao_de_dados","prazo_e_recurso"
      ]
    },

    "temas_transversais_frequentes": {
      "concurso_publico": [
        "direito_a_nomeacao_dentro_das_vagas","cadastro_de_reserva","cotas_e_criterios_objetivos",
        "tratamento_igualitario_e_pretericao","exames_psicofisicos_criterios_e_publicidade"
      ],
      "saude_e_medicamentos": [
        "fornecimento_de_medicamentos_nao_padronizados",
        "reserva_do_possivel_vs_minimo_existencial","solidariedade_entre_entes_federados"
      ],
      "educacao_e_politicas_publicas": ["creches_e_vagas","acesso_e_permanencia","transporte_escolar"],
      "trânsito_e_poder_de_policia": ["autuacoes_e_devido_processo","remocao_e_apreensao","bloqueio_de_circulacao_e_interesse_publico"]
    }
  }
}