from __future__ import annotations

"""Ontologia de Direito do Consumidor para detecção temática."""


def _load_taxonomy_consumidor() -> dict:
    # Ontologia de Direito do Consumidor (estruturada)
    return {
      "direito_do_consumidor": {
        "fundamentos_e_principios": {
          "principios_gerais": [
            "vulnerabilidade_do_consumidor",
            "boa_fe_objetiva",
            "transparencia_e_informacao_clara",
            "equilibrio_contratual",
            "harmonia_das_relacoes_de_consumo",
            "reparacao_integral"
          ],
          "direitos_basicos": [
            "proteção_da_vida_saude_e_seguranca",
            "educacao_e_informacao",
            "liberdade_de_escolha",
            "proteção_contra_publicidade_enganosa_e_abusiva",
            "alteracao_de_clausulas_desproporcionais",
            "acesso_a_orgaos_administrativos_e_justica",
            "inversao_do_onus_da_prova"
          ],
          "sujeitos_e_relacao_de_consumo": [
            "consumidor_equiparado_bystander_coletividade",
            "fornecedor_cadeia_de_fornecimento",
            "produto_e_servico_definicoes"
          ]
        },

        "responsabilidade_do_fornecedor": {
          "responsabilidade_objetiva": [
            "fato_do_produto_defeito_de_seguranca",
            "fato_do_servico_defeito_de_seguranca",
            "nexo_causal_e_excludentes",
            "solidariedade_na_cadeia"
          ],
          "vicio_do_produto_servico": [
            "vicio_de_qualidade",
            "vicio_de_quantidade",
            "prazo_de_cura_sanacao",
            "substituicao_restituicao_abatimento",
            "inutilidade_do_produto_ou_servico"
          ],
          "garantias": [
            "garantia_legal_indisponivel",
            "garantia_contratual_certificado",
            "assistencia_tecnica_prazo_e_reiteracao_do_vicio",
            "pecas_de_reposicao"
          ],
          "recall_e_seguranca": [
            "dever_de_informar_risco",
            "campanha_de_recalls",
            "autoridades_competentes_registros",
            "medidas_cautelares_de_cessacao"
          ]
        },

        "praticas_comerciais": {
          "oferta_publicidade": [
            "vinculacao_da_oferta",
            "publicidade_enganosa",
            "publicidade_abusiva",
            "marketing_infantil",
            "comparativa_e_hiperbolica",
            "orçamento_previo_vinculante"
          ],
          "vendas": [
            "venda_casada",
            "venda_por_telefone_e_porta_a_porta",
            "amostra_gratis_e_envio_nao_solicitado",
            "black_friday_precos_e_estoque",
            "preco_por_unidade_de_medida",
            "taxas_ocultas_drip_pricing"
          ],
          "cobranca_de_dividas": [
            "proibicao_de_exposicao_ao_ridiculo",
            "horarios_e_meios_licitos",
            "dano_moral_por_cobranca_abusiva",
            "cessao_de_credito_notificacao_previa"
          ],
          "servico_de_atendimento_sac": [
            "tempo_de_espera_razoavel",
            "registro_e_protocolo",
            "gravação_e_integridade_das_chamadas",
            "acessibilidade"
          ]
        },

        "contratos_e_clausulas": {
          "contratos_de_adesao": [
            "interpretacao_pro_consumidor",
            "destacado_de_clausulas_limitativas",
            "redacao_clara"
          ],
          "clausulas_abusivas": [
            "renuncia_de_direitos",
            "transf_responsabilidade_ao_consumidor",
            "limitação_indenizatória_excessiva",
            "foro_de_eleicao_que_dificulta_defesa",
            "alteracao_unilateral_lesiva",
            "indexadores_opacos_e_surpresas"
          ],
          "arbitragem_e_eleicao_de_forum": [
            "arbitragem_so_valida_se_aceitacao_especial",
            "foro_do_domicilio_do_consumidor",
            "nulos_em_hipoteses_de_hipervulnerabilidade"
          ],
          "renovacao_e_fidelizacao": [
            "renovacao_automatica_transparencia",
            "multas_de_fidelidade_proporcionalidade",
            "downgrade_e_migracao_sem_onus_oculto"
          ]
        },

        "comercio_eletronico_e_entregas": {
          "informacao_pre_contratual": [
            "identificacao_do_fornecedor",
            "caracteristicas_essenciais",
            "preco_com_desmembramento_de_custos",
            "prazo_de_entrega_estimado"
          ],
          "direito_de_arrependimento": [
            "prazo_minimo_sete_dias",
            "logistica_reversa",
            "estorno_integral_sem_custo_ao_consumidor"
          ],
          "marketplaces_e_intermediacao": [
            "responsabilidade_solidaria_em_casos_de_risco_ou_informacao_defeituosa",
            "dever_de_seguranca_e_moderação",
            "política_de_estorno_e_chargeback"
          ],
          "problemas_de_entrega": [
            "produto_nao_entregue",
            "atraso_excessivo",
            "produto_em_desacordo",
            "produto_avariado_transporte",
            "no_show_e_extravio",
            "provas_prints_rastreio_aviso_de_postagem"
          ],
          "pagamentos_online": [
            "chargeback_cartao",
            "pix_indevido_fraude",
            "boletos_falsos",
            "gateways_e_bancos_responsabilidade_concorrente"
          ]
        },

        "servicos_financeiros_bancarios": {
          "contas_cartoes_e_credito": [
            "cartao_n_enviado_e_cobranca",
            "anuidade_e_isencao_publicidade",
            "aumento_unilateral_de_limite",
            "tarifas_nao_contratadas",
            "encargos_e_juros_abusivos",
            "anatocismo_e_capitalizacao_opaca"
          ],
          "fraudes_e_seguranca": [
            "phishing_whatsapp_sim_swap",
            "transacoes_nao_reconhecidas",
            "pix_chaves_e_estelionato",
            "dever_de_seguranca_bancaria",
            "responsabilidade_por_falha_do_sistema"
          ],
          "renegociacao_e_superendividamento": [
            "diagnostico_de_superendividamento",
            "plano_de_pagamento",
            "vedacao_de_assedio_e_praticas_predatorias",
            "educacao_financeira",
            "priorizacao_de_itens_essenciais"
          ],
          "seguros_e_sinistros": [
            "dever_de_informar_coberturas_e_exclusoes",
            "negativa_indev_de_cobertura",
            "prazo_para_liquidacao",
            "seguro_cartao_e_seguro_embutido_venda_casada"
          ]
        },

        "saude_e_planos": {
          "planos_de_saude": [
            "rede_credenciada_e_referencia",
            "rol_de_procedimentos_e_cobertura_minima",
            "urgencia_e_emergencia",
            "reembolso_e_coparticipacao",
            "reajustes_anuais_e_por_faixa_etaria",
            "carencias_e_portabilidade",
            "negativa_indev_de_cobertura",
            "home_care_e_terapias_continuadas"
          ],
          "servicos_de_saude_privados": [
            "cirurgias_e_prazos",
            "orçamento_previo",
            "materiais_especificos_e_transparencia_de_precos"
          ]
        },

        "transportes_e_viagens": {
          "aereo": [
            "cancelamento_e_reembolso",
            "remarcacao_sem_multa_excessiva",
            "extravio_violacao_de_bagagem",
            "overbooking_e_negativa_de_embarque",
            "assistencia_material_atraso_conexao",
            "dano_moral_por_perda_de_evento"
          ],
          "rodoviario_e_fretamento": [
            "atraso_e_cancelamento",
            "bagagem_extravio",
            "poltronas_acessibilidade"
          ],
          "turismo_e_hospedagem": [
            "pacotes_combinados_responsabilidade_solidaria",
            "no_show_e_politicas_de_cancelamento",
            "taxas_resort_fee_ocultas"
          ]
        },

        "telecom_energia_agua_gas": {
          "telecom": [
            "qualidade_de_sinal_e_velocidade_minima",
            "franquia_de_dados_e_reducao_de_velocidade",
            "cobrança_de_servicos_nao_contratados_valor_adicionado",
            "portabilidade_e_fidelidade",
            "bloqueio_por_inadimplemento_limites"
          ],
          "energia": [
            "corte_por_inadimplemento_requisitos",
            "fatura_com_consumo_inesperado",
            "danos_por_oscilacao_ou_queda_de_energia",
            "ligacao_nova_e_prazo",
            "tarifas_e_bandeiras"
          ],
          "agua_e_esgoto": [
            "continuidade_do_servico",
            "multas_e_taxas_irregulares",
            "vicio_de_medicao_hidrômetro",
            "vazamentos_na_via_publica_responsabilidade"
          ],
          "gas": [
            "seguranca_em_instalacao",
            "interrupcao_e_religacao",
            "tarifas"
          ]
        },

        "protecao_de_dados_e_privacidade": {
          "dados_pessoais_na_relacao_de_consumo": [
            "coleta_e_base_legal",
            "finalidade_minimizacao_e_necessidade",
            "compartilhamento_com_terceiros",
            "direitos_do_titular_acesso_correção_exclusao",
            "violacao_incidente_de_seguranca_notificacao"
          ],
          "marketing_e_telemarketing": [
            "optin_optout",
            "lista_de_nao_perturbe",
            "assédio_comercial"
          ]
        },

        "protecao_do_credito": {
          "cadastros_negativos": [
            "notificacao_previa_obrigatoria",
            "exclusao_apos_quitacao",
            "prazo_maximo_de_manuntecao",
            "dano_moral_por_negativacao_indev",
            "responsabilidade_por_debito_inexistente_ou_fraude"
          ],
          "score_de_credito": [
            "transparencia_e_criterios",
            "correcao_de_dados",
            "consentimento_e_interesse_legitimo"
          ],
          "cadastros_positivos": [
            "histórico_de_pagamento",
            "beneficios_e_riscos",
            "revogacao"
          ]
        },

        "processual_consumidor": {
          "provas_e_onus": [
            "inversao_do_onus_da_prova_por_hipossuficiencia_ou_verossimilhanca",
            "cadeia_de_custodia_digital_prints_logs",
            "pericia_tecnica_produtos_servicos",
            "gravações_sac_e_protocolos"
          ],
          "tutelas_de_urgencia_e_inibitorias": [
            "suspensao_de_cobranca_e_inscricao",
            "obrigacao_de_fazer_e_nao_fazer",
            "entrega_imediata_substituicao_do_produto",
            "restabelecimento_de_servico_essencial"
          ],
          "acoes_individuais_e_coletivas": [
            "juizados_especiais_civeis",
            "acao_civil_publica",
            "substituicao_processual_por_associacoes_e_mp",
            "coisa_julgada_coletiva"
          ],
          "danos_reparacao": [
            "danos_materiais",
            "danos_morais",
            "lucros_cessantes",
            "dano_moral_coletivo"
          ],
          "acordos_e_autocomposicao": [
            "plataformas_de_conciliacao_consumidor_gov",
            "procon_mediacao",
            "tac_com_orgaos_de_defesa"
          ]
        },

        "checklists_de_prova_por_cenario": {
          "compra_online_nao_entregue": [
            "print_com_url_data_hora",
            "confirmacao_de_pedido_e_pagamento",
            "codigo_de_rastreio_ou_manifesto",
            "tentativas_de_solucao_sac_procon",
            "prazo_prometido_e_estouro"
          ],
          "produto_defeituoso_segurança": [
            "nota_fiscal",
            "laudo_e_fotos_do_defeito",
            "relato_de_risco_ou_acidente",
            "ordem_de_servico_da_assistencia",
            "registro_de_recall_se_houver"
          ],
          "negativacao_indev": [
            "comprovantes_de_quitacao",
            "print_do_cadastro_e_notificacao_previa",
            "contestacao_ao_creditor",
            "prova_de_fraude_b_o_se_houver"
          ],
          "cartao_transacao_nao_reconhecida": [
            "fatura_e_extrato",
            "registro_de_impugnacao_no_banco",
            "boletim_de_ocorrencia",
            "logs_de_localizacao_e_dispositivo"
          ],
          "plano_de_saude_negativa": [
            "pedido_medico_e_laudos",
            "negativa_formal_motivos",
            "urgencia_emergencia_comprovada",
            "orçamentos_e_prazos",
            "precedentes_ou_normas_setoriais"
          ],
          "telecom_cobranca_indev": [
            "contrato_plano_e_oferta",
            "contas_detalhadas",
            "protocolos_de_atendimento",
            "medicoes_de_velocidade"
          ],
          "energia_dano_em_eletrodomestico": [
            "comprovante_de_oscilacao_queda",
            "laudo_tecnico_do_aparelho",
            "protocolo_na_concessionaria",
            "orcamento_de_conserto_substituicao"
          ]
        }
      }
    }


_CONSUMIDOR_ONTOLOGY = _load_taxonomy_consumidor()