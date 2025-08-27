# Patch unificado: meu_app (models + persistence + services)
Data: 2025-08-26

## O que está incluso
- `meu_app/models/cliente.py`
- `meu_app/models/historico.py`
- `meu_app/models/__init__.py`
- `meu_app/persistence/db.py` (corrigido e alinhado aos repositórios)
- `meu_app/persistence/repositories.py` (sua versão enviada)
- `meu_app/persistence/__init__.py`
- `meu_app/services/*` (imports robustos, indexador FAISS e buscador de contexto)

## Como aplicar
1. Extraia este ZIP **dentro da pasta do projeto**:
   `C:\Users\Larissa Moura\Documents\meu_app\`
   Ficará assim:
   ```
   meu_app\
     __init__.py
     models\...
     persistence\...
     services\...
   main.py         (seu arquivo atual na raiz, permanece)
   ```

2. Ajuste `server.py` (se existir) para usar imports absolutos do pacote, por exemplo:
   ```python
   from meu_app.persistence.db import insert_webhook_log
   # e similares
   ```

3. (Opcional) Crie/ative o venv e instale dependências mínimas:
   ```powershell
   cd "C:\Users\Larissa Moura\Documents\meu_app"
   # .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip

   # PDF e FAISS
   pip install "pymupdf>=1.24,<1.26" faiss-cpu

   # LangChain + OpenAI embeddings
   pip install "langchain-openai>=0.1.7" "langchain-community>=0.2.0" openai

   # Tavily (opcional para busca web)
   pip install tavily-python
   ```

4. Configure variáveis de ambiente (exemplos PowerShell):
   ```powershell
   $env:OPENAI_API_KEY = "<sua_chave>"
   $env:PDFS_DIR = "data/pdfs"
   $env:INDEX_DIR = "index/faiss_index"
   # (opcional)
   # $env:TAVILY_API_KEY = "<sua_chave>"
   ```

5. Reconstrua e verifique o índice:
   ```powershell
   py .\main.py rebuild-index
   py .\main.py index-info
   ```

6. Teste um preview de proposta (usa contexto dos PDFs):
   ```powershell
   py .\main.py preview-proposal --nome "Maria" --resumo "Ação de alimentos" --valor 25000
   ```

### Observações
- Os imports internos foram padronizados (relativos + fallback absoluto) para funcionar tanto rodando `py .\main.py` quanto, no futuro, `py -m meu_app.main` se você mover o `main.py` para dentro do pacote.
- O schema do SQLite agora está compatível com os repositórios (tabelas: clientes, contatos, mensagens, propostas, propostas_eventos, payments, payments_events).
- Se aparecer erro de import de `pricing`, o `ConversorPropostas` já possui **fallback** embutido (usa heurística) até você ter um `services/pricing.py` próprio.
