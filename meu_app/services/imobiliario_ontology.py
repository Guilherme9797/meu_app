"""Ontologia de Direito Imobiliário para detecção temática."""

_IMOBILIARIO_ONTOLOGY = {
    "direito_imobiliario": {
        "propriedade_posse_e_direitos_reais": {
            "propriedade": [
                "aquisicao_derivada_compra_e_venda_doacao_sucessao",
                "aquisicao_originaria_usucapiao",
                "perda_da_propriedade",
                "funcao_social_da_propriedade",
                "desapropriacao_utilidade_interesse_social",
            ],
            "posse": [
                "posse_nova_e_velha",
                "posse_de_boafe_e_mafe",
                "interditos_possessorios_manutencao_reintegracao_interdito_proibitorio",
                "esbulho_turbacao_ameaça",
                "acessio_possessionis",
            ],
            "direitos_reais_limitados": [
                "servidao_passagem_luz_agua",
                "superficie_urbana_rural",
                "direito_real_de_laje",
                "usufruto_uso_habitacao",
                "enfiteuse_enfitêutico_resíduos",
            ],
        },
        "registro_de_imoveis_e_titulacao": {
            "principios_registrais": [
                "especialidade_objetiva_e_subjetiva",
                "continuidade",
                "prioridade_prenotacao",
                "legalidade",
                "fé_publica_registral",
                "concentracao_na_matricula",
            ],
            "atos_registrais_comuns": [
                "abertura_de_matricula",
                "registro_de_transferencia",
                "averbacao_de_construcao_e_habite_se",
                "averbacao_de_obras_reformas_e_demolicao",
                "averbacao_de_estado_civil_e_convenção_antenuptial",
                "averbacao_de_penhora_hipoteca_e_usufruto",
                "indisponibilidade",
                "cancelamento_e_retificacao",
            ],
            "retificacao_registral": [
                "art_213_lrp_planta_e_memorial",
                "retificacao_consensual",
                "retificacao_contenciosa",
                "notificacao_de_confinantes",
            ],
            "usucapiao_extrajudicial": [
                "ata_notarial_posse_mansa_e_pacifica",
                "planta_memorial_anuencia_confinantes",
                "certidoes_negativas",
                "justo_titulo_e_boafe_nao_obrigatorios",
                "impugnacao_e_remessa_ao_judiciario",
            ],
            "adjudicacao_compulsoria": [
                "promessa_de_compra_e_venda_registrada",
                "recusa_injustificada_do_alienante",
                "judicial_e_extrajudicial",
                "sentenca_mandamental_titulo_registravel",
            ],
        },
        "contratos_imobiliarios": {
            "promessa_compra_e_venda": [
                "sinal_arras",
                "arrependimento_e_perdas_e_danos",
                "clausula_penal",
                "adjudicacao_compulsoria",
                "resolucao_por_inadimplemento",
            ],
            "compra_e_venda_definitiva": [
                "escritura_publica",
                "registro_na_matricula_efetiva_a_translacao",
                "eviccao_imobiliaria",
                "impostos_itbi_itcmd",
            ],
            "permuta_e_dacao_em_pagamento": [
                "permuta_com_torno",
                "permuta_por_area_construida",
                "tributacao_e_efeitos_registrais",
            ],
            "corretagem": [
                "deveres_do_corretor",
                "comissao_condicao_devida",
                "taxa_sati_abusividade",
            ],
            "garantias_reais": [
                "hipoteca",
                "alienacao_fiduciaria_imobiliaria_lei_9514_97",
                "anticrese",
                "penhor_atipico_de_direitos",
            ],
        },
        "financiamento_e_alienacao_fiduciaria": {
            "sistemas_de_financiamento": [
                "sfh",
                "sfi",
                "cédula_de_credito_imobiliario",
                "taxas_e seguros_mip_dfi",
            ],
            "alienacao_fiduciaria_lei_9514_97": [
                "contrato_e_registro_na_matricula",
                "mora_e_constituicao_por_interpelacao",
                "intimacao_fiduciante",
                "consolidacao_da_propriedade_em_nome_do_fiduciario",
                "leilao_extrajudicial_1a_e_2a_praca",
                "saldo_residual_e_restituicao",
                "purgação_da_mora_limites",
                "nulidades_formais_no_procedimento",
            ],
            "execucao_e_leiloes": [
                "leilao_judicial_x_extrajudicial",
                "posse_e_imissao_do_arrematante",
                "sub-rogacao_nas_condominio_e_iptu",
                "tutela_de_urgencia_para_suspender_leilao",
            ],
        },
        "incorporacao_e_construcao": {
            "incorporacao_imobiliaria_lei_4591_64": [
                "registro_do_memorial_de_incorporacao",
                "patrimonio_de_afetacao",
                "publicidade_e_prospeccao",
                "garantias_ao_adquirente",
            ],
            "condominio_edilicio": [
                "convencao_e_regimento_interno",
                "quoruns_para_obras_necessarias_uteis_voluptuarias",
                "assembleias_convocacao_quorum_e_impugnacao",
                "fracao_ideal_vagas_de_garagem_autonomas_e_acessorias",
                "animais_domesticos_e_uso_anormal_da_unidade",
                "locacao_por_temporada_airbnb_regras_e_quorum",
                "cobranca_de_cotas_condominiais_multa_e_juros",
                "penhora_da_unidade_por_divida_de_cotas",
                "responsabilidade_por_vicios_em_areas_comuns",
            ],
            "loteamento_e_parcelamento_do_solo": [
                "lei_6766_79",
                "aprovacao_municipal_e_registro",
                "obras_de_infraestrutura",
                "deveres_do_loteador",
                "resolucao_por_atraso_de_obras",
            ],
            "multipropriedade_lei_13777_18": [
                "instituicao_e_convencao",
                "uso_exclusivo_por_periodos",
                "administracao_e_rateio",
                "alienacao_e_garantias",
            ],
            "shopping_center_e_built_to_suit": [
                "clausulas_atipicas",
                "aluguel_percentual_e_fundo_de_promocao",
                "reajuste_e_renovacao",
                "equilibrio_economico_financeiro",
            ],
        },
        "vicios_construtivos_atraso_e_distrato": {
            "vicios_construtivos": [
                "solidez_e_seguranca_nbr_15575",
                "prazo_de_garantia_e_prescricao",
                "responsabilidade_construtora_incorporadora",
                "seguro_habitacional_sfh_cobertura_de_vicios",
                "pericia_engenharia_prova_fotografica_e_videos",
            ],
            "atraso_de_obra": [
                "clausula_de_tolerancia",
                "lucros_cessantes_e_aluguel_social",
                "astreintes",
                "forca_maior_caso_fortuito_limites",
            ],
            "distrato_lei_13786_18": [
                "percentuais_de_retenção",
                "prazo_de_restituicao",
                "correcao_monetaria_e_juros",
                "culpa_do_comprador_vs_culpa_do_vendedor",
                "clausula_penal_inversa",
            ],
        },
        "locacao_urbana_lei_8245_91": {
            "contratacao_e_garantias": [
                "locacao_residencial_e_nao_residencial",
                "caucao_fianca_seguro_fianca_titulo_de_capitalizacao",
                "fiador_bem_de_familia_penhorabilidade_excecao",
                "benfeitorias_necessarias_uteis_voluptuarias",
            ],
            "execucao_e_despejo": [
                "acao_de_despejo_falta_de_pagamento",
                "despejo_por_denuncia_vazia",
                "liminar_art_59",
                "consignacao_em_pagamento",
                "reintegracao_de_posse_x_despejo",
            ],
            "revisional_e_renovatoria": [
                "acao_revisional_aluguel_valor_de_mercado",
                "acao_renovatoria_prazo_e_requisitos",
                "shopping_center_especificidades",
            ],
            "direito_de_preferencia": [
                "alienacao_do_imovel",
                "prazo_e_formalidades",
                "perda_da_preferencia_e_perdas_e_danos",
            ],
        },
        "regularizacao_fundiaria_e_rural": {
            "reurb_lei_13465_17": [
                "reurb_s_interesse_social",
                "reurb_e_interesse_especifico",
                "legitimados_procedimento",
                "projeto_urbanistico_memorial_descritivo",
                "matriculas_individuais_pos_reurb",
            ],
            "imoveis_rurais": [
                "georreferenciamento_incra",
                "ccir_itr",
                "car_reserva_legal_e_app",
                "servidoes_ambientais",
                "retificacao_de_area_rural",
            ],
            "regularizacao_cartorial": [
                "usucapiao_familiar",
                "reconhecimento_de_domínio",
                "dúvida_registral_corregedoria",
            ],
        },
        "responsabilidade_e_litigios_frequentes": {
            "bem_de_familia": [
                "impenhorabilidade_regra_geral",
                "excecao_fianca_locatícia",
                "outras_excecoes_creditos",
                "descaracterizacao_por_imovel_de_alto_padrao_ou_imovel_luxo_nao_residencial",
            ],
            "condominio_cobranca": [
                "prova_da_divida_planilha_cotas",
                "multa_convencional_e_juros",
                "protesto_e_negativacao",
                "execucao_titulo_extrajudicial",
            ],
            "responsabilidade_por_vizinhança": [
                "uso_anormal_da_propriedade",
                "barulho_odor_infiltracoes",
                "obra_irregular_e_abnt",
                "pericia_engenharia",
            ],
            "contencioso_registral": [
                "dúvida_registral",
                "recusa_de_registro_ou_averbacao",
                "conflito_de_principios_registrais",
                "suscitacao_ao_judiciario",
            ],
        },
        "tributos_e_encargos_reais": {
            "iptu": [
                "sujeito_passivo_proprietario_possuidor_promitente_comprador",
                "progressividade_e_planta_de_valores",
                "imunidades_e_isencoes",
            ],
            "itbi": [
                "fato_gerador_promessa_vs_escritura",
                "base_de_calculo_valor_de_mercado",
                "imunidade_na_integracao_de_capital_e_holding_imobiliaria_limites",
            ],
            "itcmd": [
                "doacao_e_sucessao",
                "competencia_estadual",
                "base_de_calculo_e_isencoes",
            ],
            "taxas_e_contribuicoes": [
                "melhorias",
                "limpeza_publica",
                "iluminacao",
            ],
        },
        "checklists_de_prova_por_cenario": {
            "adjudicacao_compulsoria": [
                "contrato_promessa_com_provas_de_quitacao",
                "notificacao_previa_do_vendedor",
                "certidoes_negativas",
                "matricula_e_cadeia_dominial",
            ],
            "usucapiao_extrajudicial": [
                "ata_notarial",
                "planta_memorial_assinados",
                "certidoes_negativas",
                "anuencias_confinantes_ou_justificativa",
                "fotos_e_testemunhas",
            ],
            "atraso_de_obra": [
                "contrato_memorial_e_cronograma",
                "emails_notificacoes",
                "fotos_videos_e_relatorios_de_engenharia",
                "comprovantes_de_aluguel_social",
                "publicidade_ofertas",
            ],
            "vicios_construtivos": [
                "relatorio_tecnico_nbr_15575",
                "fotos_e_videos",
                "ordem_de_servico_e_orcamentos",
                "apolice_sfh_se_coberta",
            ],
            "despejo_por_falta_de_pagamento": [
                "contrato_de_locacao",
                "planilha_de_debito_cotas_e_alugueis",
                "comprovacao_de_mora_notificacao",
                "fianca_e_bens_do_fiador",
            ],
            "leilao_extrajudicial_fiduciario": [
                "contrato_e_matricula_com_alienacao_fiduciaria",
                "provas_de_intimacao_regular",
                "edital_e_ata_de_leilao",
                "planilha_de_debito",
                "nulidades_formais",
            ],
        },
    }
}

