"""Ontologia simplificada de Direito Processual Penal para detecção temática."""

_PROC_PENAL_ONTOLOGY = {
  "direito_processual_penal": {
    "sistemas_e_principios": {
      "sistemas_processuais": ["inquisitorial", "acusatorio", "misto"],
      "principios_constitucionais": [
        "presuncao_de_inocencia","contraditorio","ampla_defesa","publicidade_dos_atos",
        "busca_da_verdade_real","favor_rei","juiz_natural","proporcionalidade",
        "livre_convencimento_motivado","liberdade_probatória"
      ]
    },

    "lei_processual_penal": {
      "fontes": ["constitucionais","legais_codigos_e_leis_extravagantes","jurisprudenciais_e_supletivas"],
      "aplicacao_no_tempo": ["tempus_regit_actum","ultraatividade","retroatividade_benefica"],
      "aplicacao_no_espaco": ["territorialidade","extraterritorialidade_relativa"],
      "interpretacao": ["gramatical","sistemática","teleológica","analogia_in_bonampartem","aplicacao_subsidiaria_do_cpc"]
    },

    "juiz_das_garantias": {
      "conceito": ["fase_preprocessual","juiz_diferente_do_merito"],
      "atribuicoes": ["controle_de_legalidade_da_investigacao","decisoes_sobre_prisoes","autorizacao_de_interceptacoes","validacao_de_provas"],
      "competencia": ["delimitacao_ate_recebimento_da_denuncia","separacao_funcoes"]
    },

    "investigacao_criminal": {
      "inquerito_policial": ["conceito","natureza_juridica","finalidade","valor_probatório","dispensabilidade"],
      "caracteristicas": ["oficiosidade","inquisitorialidade","sigilosidade","indisponibilidade","discricionariedade","escrita"],
      "presidencia": ["autoridade_policial","competencia_da_policia_federal_e_civil"],
      "policia_judiciaria": ["competencias","limites_constitucionais","controle_externo_mp"],
      "meios_investigativos": ["busca_e_apreensao","interceptacao_telefonica_telematica","quebra_de_sigilo_bancario_e_fiscal","colaboracao_premiada","agente_infiltrado","acao_controlada"],
      "cadeia_de_custodia": ["definicao","etapas_recolhimento_armazenamento_preservacao","nulidade_por_violacao"]
    },

    "acao_penal": {
      "tipos": ["publica_incondicionada","publica_condicionada_representacao","condicionada_requisicao_ministro_justica","privada","privada_personalissima","privada_subsidiaria_da_publica"],
      "denuncia_e_queixa": ["requisitos_denuncia","requisitos_queixa","aditamento","recebimento_e_rejeicao"],
      "principios": ["indivisibilidade","oportunidade_representacao","indisponibilidade"]
    },

    "prisao_e_medidas_cautelares": {
      "prisao_em_flagrante": ["requisitos","formalidades","relatorio_de_prisao","conversao_em_preventiva"],
      "prisao_preventiva": ["fumus_commissi_delicti","periculum_libertatis","garantia_da_ordem_publica","garantia_da_ordem_economica","conveniencia_da_instrucao","assegurar_aplicacao_da_lei_penal"],
      "prisao_temporaria": ["crimes_cabiveis","prazo","prorrogacao"],
      "prisao_domiciliar": ["idoso","mae_de_menor","gravida","doenca_grave"],
      "medidas_cautelares_diversas": ["comparecimento_periodico_em_juizo","proibicao_de_acesso_a_lugares","proibicao_de_contato","suspensao_do_exercicio_funcao","monitoramento_eletronico"],
      "audiencia_de_custodia": ["controle_da_legalidade","verificacao_de_maus_tratos","analise_de_medidas_cautelares"],
      "revogacao_e_substituicao": ["perda_do_motivo","medidas_menos_gravosas"]
    },

    "provas": {
      "provas_em_geral": ["principio_da_liberdade_probatória","licitude","exame_de_corpo_de_delito","testemunhal","documental","pericial"],
      "provas_digitais": ["cadeia_de_custodia","logs","dados_extraidos_de_celulares","prints_e_autenticacao"],
      "meios_de_obtencao": ["busca_e_apreensao","interceptacao","colaboracao_premiada","infiltracao_virtual","acao_controlada"],
      "provas_ilicitas": ["exclusao_por_ilicitude","teoria_dos_frutos_da_arvore_envenenada","provas_derivadas_licitas"]
    },

    "procedimentos": {
      "rito_ordinario": ["denuncia","citacao","resposta_a_acusacao","audiencia_de_instrução_e_julgamento","sentenca"],
      "rito_sumario": ["hipoteses","prazos_reduzidos","julgamento_celere"],
      "rito_simplificado": ["contravencoes","pequena_complexidade"],
      "procedimentos_especiais": {
        "tribunal_do_juri": ["judicium_accusationis_pronuncia_impronuncia","absolvicao_sumaria","desclassificacao","judicium_causae_plenario","quesitacao","soberania_dos_veredictos"],
        "crimes_de_responsabilidade": ["processo_dos_funcionarios_publicos","foro_por_prerrogativa"],
        "leis_especiais": ["lei_de_drogas_rito","lei_de_crimes_hediondos","lei_maria_da_penha","estatuto_do_idoso","estatuto_da_crianca_e_adolescente"]
      }
    },

    "recursos_e_impugnacoes": {
      "recursos_em_geral": ["efeito_devolutivo_e_suspensivo","regra_do_duplo_grau","fungibilidade","desercao","reformatio_in_pejus"],
      "recurso_em_sentido_estrito": ["decisoes_cabiveis","prazo","juizo_de_retratacao"],
      "apelacao": ["hipoteses","efeito_devolutivo","sustentacao_oral"],
      "embargos": ["declaracao","infringentes"],
      "recursos_aos_tribunais_superiores": ["recurso_especial","recurso_extraordinario","agravo_em_REsp","agravo_em_RE"],
      "acao_autonoma_de_impugnacao": ["habeas_corpus","revisao_criminal","mandado_de_segurança"]
    },

    "justica_consensual": {
      "colaboracao_premiada": ["premios_reducao_de_pena","requisitos_eficacia","controle_judicial"],
      "acordo_de_nao_persecucao_penal": ["hipoteses_de_cabimento","condicoes","homologacao"],
      "transacao_penal": ["juizados_especiais_criminais","requisitos"],
      "suspensao_condicional_do_processo": ["hipoteses","prazo","condicoes"]
    },

    "nulidades_processuais": {
      "conceito": ["nulidade_absoluta_relativa","teoria_do_prejuizo","convalidacao"],
      "casos": ["ausencia_de_defesa_tecnica","citacao_nula","violacao_ao_contraditorio"]
    }
  }
}
