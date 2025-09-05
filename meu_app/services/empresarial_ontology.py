"""Ontologia de Direito Empresarial para detecção temática."""

_EMPRESARIAL_ONTOLOGY = {
  "direito_empresarial": {
    "teoria_geral_da_empresa": {
      "conceito_de_empresa": [
        "atividade_economica_organizada",
        "empresario_individual",
        "microempreendedor_individual_mei",
        "profissoes_intelectuais_nao_empresariais"
      ],
      "estabelecimento": [
        "fundo_de_comercio","aviamento","trespasse","contrato_de_exploracao"
      ],
      "nome_empresarial": [
        "firma","denominacao","protecao_e_registro","colisao_com_marca"
      ],
      "capacidade_e_impedimentos": [
        "empresario_menor_emancipado","incapacidade_relativa_absoluta","proibicoes_legais"
      ]
    },

    "registro_empresarial": {
      "junta_comercial": ["competencias","atos_registraveis","certidoes"],
      "escrituracao": ["livros_obrigatorios","balanco_patrimonial","livro_diario","autenticacao_digital"],
      "obrigacoes_contabeis": ["principios_contabeis","escrituracao_regular_irregular","valor_probatório_dos_livros"]
    },

    "sociedades": {
      "sociedade_em_comum": ["caracteristicas","responsabilidade_dos_socios","eficacia_perante_terceiros"],
      "sociedade_simples": ["registro","responsabilidade","contrato_social"],
      "sociedade_limitada": ["contrato_social","capital_social","administracao","responsabilidade_dos_socios","conselho_fiscal","quotas_e_cedencia"],
      "sociedade_anonima": {
        "acoes": ["ordinarias_preferenciais","nominativas_ao_portador","direitos_e_deveres_dos_acionistas"],
        "assembleia_geral": ["ordinaria","extraordinaria","competencias"],
        "conselho_de_administracao": ["atribuições","responsabilidade_dos_administradores"],
        "diretoria": ["representacao","competencias"],
        "conselho_fiscal": ["funcao_fiscalizadora","relatorios"],
        "debentures_e_bonus_de_subscricao": ["emissao","direitos_dos_titulares"]
      },
      "sociedade_em_comandita": ["simples","por_acoes"],
      "sociedade_unipessoal_limitada": ["constituição","responsabilidade_limitada"],
      "cooperativas": ["principios","responsabilidade_dos_cooperados"],
      "transformacao_fusao_cisao_incorporacao": ["conceito_e_diferencas","procedimentos","efeitos_juridicos"],
      "dissolucao_e_liquidacao": ["causas","nomeacao_de_liquidante","prestacao_de_contas"]
    },

    "titulos_de_credito": {
      "principios": ["cartularidade","literalidade","autonomia","abstracao"],
      "letra_de_cambio": ["sacador","sacado","endosso","aval"],
      "nota_promissoria": ["requisitos_formais","endosso","aval"],
      "cheque": ["emissao","compensacao","sustacao","protesto"],
      "duplicata": ["emissao","aceite","protesto","execucao"],
      "endosso": ["translativo","mandato","caucao"],
      "aval": ["responsabilidade_solidaria","execucao"],
      "protesto": ["efeitos","prazo","cancelamento"]
    },

    "contratos_empresariais": {
      "distribuicao": ["exclusividade","responsabilidade_pelas_vendas"],
      "representacao_comercial": ["agencia","mediação","indenizacao_por_rescisao"],
      "franquia": ["lei_de_franquias","circular_de_oferta","responsabilidade_do_franqueador"],
      "leasing": ["arrendamento_mercantil","financeiro","operacional"],
      "factoring": ["cessao_de_credito","assuncao_de_risco","proibicao_de_fomento_comercial"],
      "joint_ventures_e_parcerias": ["contratos_de_cooperacao","clausula_de_nao_concorrencia","transferencia_de_tecnologia"]
    },

    "propriedade_industrial": {
      "marcas": ["registro_inpi","uso_exclusivo","nulidade","colisao_com_nome_empresarial"],
      "patentes": ["inovacao","modelo_de_utilidade","prazo_de_vigencia","licenciamento"],
      "desenho_industrial": ["registro","proteção","nulidade"],
      "indicacao_geografica": ["denominacao_de_origem","indicacao_de_procedencia"],
      "concorrencia_desleal": ["parasitismo","confusao","segredo_industrial","exploracao_de_clientela"]
    },

    "crise_da_empresa": {
      "recuperacao_judicial": ["requisitos","plano_de_recuperacao","assembleia_de_credores","classes_de_credores","cram_down"],
      "recuperacao_extrajudicial": ["homologacao","negociacao_privada"],
      "falencia": ["requisitos","convolacao_em_falencia","classificacao_de_creditos","quadro_geral_de_credores","arrecadacao_de_bens","realizacao_do_ativo","extincao_das_obrigacoes"],
      "responsabilidade_dos_administradores": ["atos_fraudulentos","desconsideracao_da_personalidade","responsabilidade_civil_e_penal"]
    },

    "temas_modernos": {
      "governanca_corporativa": ["compliance","auditoria","transparencia"],
      "direito_concorrencial": ["abuso_de_poder_economico","cartel","dumping","atos_de_concentracao_cade"],
      "sociedade_digital": ["empresas_de_tecnologia","proteção_de_dados_lgpd","blockchain_contratos_inteligentes"]
    }
  }
}