# App Jurídico – Etapa 1 (Atendimento Inicial)

Pipeline da Etapa 1:
1) **Atendimento inicial** → registra histórico, identifica o problema do cliente (OpenAI)  
2) **Base interna (PDFs)** → busca trechos relevantes (FAISS + embeddings)  
3) **Fallback externo** → se necessário, pesquisa via Tavily  
4) **Refinamento** → reescreve a resposta de forma clara e objetiva (OpenAI)  
5) **Persistência** → salva cliente/mensagens em SQLite  
6) **Canais** → API HTTP e WhatsApp via **Z-API** (com webhook)  

> A arquitetura é modular (orientada a objetos), para evoluir depois para Conversão, Fechamento e Onboarding.

---

## ✨ Principais recursos

- **ID único por cliente** (`models/cliente.py`)
- **Histórico persistente** por cliente em **SQLite** (repositórios em `persistence/`)
- **Indexação de PDFs** com **FAISS + OpenAI embeddings**
  - **Atualização incremental** (detecta PDFs novos)  
  - **Rebuild automático** se houver PDFs removidos/alterados
  - Métricas de indexação (tempo, chunks)
- **Fallback Tavily** para buscas externas
- **Refinamento** de respostas com OpenAI (linguagem simples, coerente)
- **WhatsApp (Z-API)**: recebe mensagens via webhook e responde automaticamente
- **ngrok**: túnel público, configura webhook Z-API automaticamente
- **API HTTP** com rotas de **saúde**, **métricas**, **atendimento** e **admin** (token)
- **Segurança**: endpoints administrativos protegidos por `ADMIN_API_KEY`
- **Observabilidade**: logs estruturados (JSON), `/health` enriquecido e `/metrics` (formato Prometheus simples)
- **Deploy**: Dockerfile multi-stage + `docker-compose.yml` (proxy HTTPS com nginx-proxy + acme-companion)

---

## ⚙️ Requisitos

- **Python 3.11+**
- Acesso a chaves:
  - `OPENAI_API_KEY` (obrigatório)
  - `TAVILY_API_KEY` (opcional)
  - `ZAPI_INSTANCE_ID`, `ZAPI_TOKEN` (para WhatsApp via Z-API)
  - (Opcional) **ngrok** (`NGROK_AUTHTOKEN`, `NGROK_DOMAIN`) para testes locais com webhook público


Instale as dependências:
```bash
pip install -r requirements.txt
# meu_app

```

### Variáveis adicionais
- `INDEX_DIR`: caminho para o índice FAISS (padrão `index/faiss_index`)
- `RAG_MIN_CHUNK_SCORE`: descarta trechos abaixo desse score (padrão `0.3`)
- `RAG_PER_DOC_CAP`: limite de trechos por documento (padrão `3`)
- `RAG_MMR_LAMBDA`: pondera relevância/diversidade na seleção (padrão `0.6`)