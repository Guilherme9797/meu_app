"""Ontologia de Direito Tributário para detecção temática."""

_TRIBUTARIO_ONTOLOGY = {
    "direito_tributario": {
        "fundamentos_e_principios": {
            "principios_constitucionais": [
                "legalidade_tributaria",
                "anterioridade",
                "anterioridade_nonagesimal",
                "irretroatividade",
                "isonomia",
                "capacidade_contributiva",
                "vedacao_ao_confisco",
                "progressividade",
                "seletividade",
                "uniformidade_geografica",
            ],
            "principios_infraconstitucionais": [
                "simplicidade",
                "transparencia_fiscal",
                "cooperacao_fisco_contribuinte",
            ],
        },
        "competencia_tributaria": {
            "competencia_da_uniao": [
                "impostos_federais",
                "taxas_federais",
                "contribuicoes_especiais",
            ],
            "competencia_dos_estados_df": ["icms", "ipva", "itcmd"],
            "competencia_dos_municipios": [
                "iss",
                "iptu",
                "itbi",
                "taxas_municipais",
            ],
            "competencia_residual_da_uniao": [
                "novos_impostos",
                "contribuicoes_residuais",
            ],
            "limitacoes_ao_poder_de_tributar": [
                "imunidades",
                "competencia_exclusiva",
                "vedacao_de_tributos_confiscatorios",
            ],
        },
        "obrigacao_tributaria": {
            "conceito": [
                "vinculo_juridico_fisco_contribuinte",
                "obrigacao_principal",
                "obrigacao_acessoria",
            ],
            "sujeitos": [
                "ativo",
                "passivo_direto",
                "responsavel_tributario",
                "solidariedade",
            ],
            "fato_gerador": [
                "hipotese_de_incidencia",
                "momento_de_ocorrencia",
                "diferenciacao_entre_incidente_e_excluido",
            ],
            "credito_tributario": [
                "constituicao_pelo_lancamento",
                "suspensao",
                "extincao",
                "exclusao",
                "garantias_e_privilegios",
            ],
        },
        "lancamento_tributario": {
            "modalidades": ["de_oficio", "por_declaracao", "por_homologacao"],
            "revisao": ["lancamento_supletivo", "revisao_por_erro", "nulidade_e_inexistencia"],
        },
        "responsabilidade_tributaria": {
            "solidaria": ["varios_sujeitos_passivos", "beneficio_de_ordem"],
            "sucessores": [
                "responsabilidade_por_sucessao_causa_mortis",
                "responsabilidade_por_sucessao_empresarial",
                "incorporacao_fusao_cisao",
            ],
            "terceiros": [
                "administradores_socios",
                "responsabilidade_por_infrazão",
                "responsabilidade_por_substituicao_tributaria",
            ],
            "retencao_na_fonte": ["irrf", "iss_retido", "contribuicoes_sociais_retidas"],
        },
        "prescricao_e_decadencia": {
            "decadencia": [
                "prazo_art_150_paragrafo_4",
                "prazo_art_173_i",
                "contagem_e_marcos_interruptivos",
            ],
            "prescricao": [
                "prazo_quinquenal",
                "prescricao_intercorrente",
                "suspensao_interrupcao",
                "renuncia_e_renovacao",
            ],
        },
        "especies_tributarias": {
            "impostos": {
                "icms": [
                    "hipotese_de_incidencia",
                    "mercadorias_servicos_comunicacao_energia",
                    "substituicao_tributaria",
                    "difal_diferencial_de_aliquotas",
                    "creditos_e_compensacao",
                    "beneficios_fiscais",
                ],
                "ipi": ["industrializacao", "seletividade", "creditos_presumidos"],
                "ir": [
                    "pessoa_fisica",
                    "pessoa_juridica",
                    "ganho_de_capital",
                    "isencoes_e_deducoes",
                ],
                "iss": [
                    "lista_de_servicos",
                    "local_da_prestacao",
                    "retencao_na_fonte",
                    "planos_de_saude_cartoes_de_credito",
                ],
                "iptu": [
                    "fato_gerador_propriedade_urbana",
                    "progressividade_fiscal",
                    "imunidade_templos_entidades",
                ],
                "itbi": [
                    "transmissao_inter_vivos",
                    "base_de_calculo",
                    "imunidades",
                ],
                "itcmd": ["doacao", "heranca", "competencia_estadual"],
                "ipva": ["propriedade_de_veiculo", "responsabilidade_solidaria", "imunidades"],
            },
            "taxas": [
                "exercicio_do_poder_de_policia",
                "utilizacao_de_servico_publico_especifico_divisivel",
                "custas_e_emolumentos",
            ],
            "contribuicoes": [
                "contribuicoes_sociais",
                "contribuicoes_de_intervencao_no_dominio_economico",
                "contribuicoes_de_categoria_profissional",
            ],
            "emprestimos_compulsorios": [
                "calamidade_publica",
                "guerra_externa",
                "investimento_publico_relevante",
            ],
            "contribuicao_de_melhoria": [
                "obra_publica",
                "valorizacao_imobiliaria",
                "limite_do_custo_total",
            ],
        },
        "processo_administrativo_fiscal": {
            "lancamento_e_impugnacao": [
                "auto_de_infracao",
                "defesa_do_contribuinte",
                "julgamento_administrativo",
            ],
            "recursos": ["conselhos_de_contribuintes", "carf", "efeito_suspensivo"],
        },
        "execucao_fiscal": {
            "lei_6830_1980": [
                "certidao_da_divida_ativa",
                "presuncao_de_liquidez_e_certeza",
                "citacao",
                "penhora",
                "prazo_para_embargos",
            ],
            "embargos_do_devedor": [
                "cabimento",
                "efeito_suspensivo",
                "excesso_de_execucao",
                "ilegitimidade_passiva",
            ],
            "excecao_de_pre_executividade": [
                "matéria_de_ordem_publica",
                "ilegitimidade_manifestada",
                "nulidade_formal",
            ],
            "garantias_da_execucao": [
                "penhora_online_sisbajud",
                "arresto",
                "hipoteca_legal",
                "seguro_garantia_fianca_bancaria",
            ],
        },
        "beneficios_e_incentivos": {
            "isencao": ["legal", "convencional"],
            "anistia": ["perdao_de_creditos_tributarios", "limites"],
            "remissao": ["extincao_por_equidade", "hipossuficiencia"],
            "transacao_tributaria": [
                "parcelamento",
                "negociacao_de_creditos",
                "programas_de_recuperacao_fiscal_refis",
            ],
        },
    }
}