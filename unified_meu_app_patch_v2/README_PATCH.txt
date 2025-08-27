Patch v2 — 2025-08-26
- Atualiza persistence/db.py (webhook_logs + migração de coluna 'criado_em' em contatos + insert_webhook_log())
- Adiciona services/pricing.py (PricingService/PricingInput com minimo_brl/sugerido_brl)
- Adiciona services/payments/ (providers fictícios p/ dev)
- Atualiza services/analisador.py (método .analisar())
- Atualiza services/buscador_pdf.py (aceita pasta_pdfs/pasta_index)
- Atualiza services/zapi_client.py (reply_to_message_id)
- Fornece .env.example e requirements.txt sanitizados
