# =========================
# Variáveis
# =========================
# Detecta caminhos do venv por SO
ifeq ($(OS),Windows_NT)
	VENV_BIN=venv\Scripts
	PY=$(VENV_BIN)\python.exe
	PIP=$(VENV_BIN)\pip.exe
	ACTIVATE=venv\Scripts\activate
	SLEEP=$(PY) -c "import time; time.sleep(2)"
	SHELL:=cmd.exe
	SHELLFLAGS:=/C
else
	VENV_BIN=venv/bin
	PY=$(VENV_BIN)/python
	PIP=$(VENV_BIN)/pip
	ACTIVATE=. venv/bin/activate
	SLEEP=sleep 2
endif

PORT?=5000
ADMIN_API_KEY?=dev-secret
DOMAIN?=localhost
CURL?=curl -sS
COMPOSE?=docker compose
PDF_SRC_DIR?=data/pdfs
RAG_INDEX_PATH?=index/faiss_index
EMBED_MODEL?=text-embedding-3-small

# Para db_admin
DB_OUTDIR?=backups
TABLE?=
QUERY?=
LIMIT?=20

# =========================
# Ajuda
# =========================
.PHONY: help
help:
	@echo "Targets úteis:"
	@echo "  venv                - cria venv"
	@echo "  install             - instala dependências no venv"
	@echo "  run                 - roda o servidor Flask (server.py)"
	@echo "  run-ngrok           - Flask + ngrok (configura webhook na Z-API)"
@echo "  health              - GET /health"
@echo "  metrics             - GET /metrics"
@echo "  update-index        - POST /update-index (X-API-Key)"
@echo "  rebuild-index       - POST /rebuild-index (X-API-Key)"
@echo "  index               - (re)constrói o índice FAISS a partir de data/pdfs"
@echo "  index-status        - mostra status do índice"
	@echo "  webhook-config      - POST /zapi/configure-webhooks (X-API-Key)"
	@echo "  certs-dev           - gera cert autoassinado p/ DOMAIN"
	@echo "  certs-install       - instala fullchain/privkey em data/certs (vars: CERT, KEY)"
	@echo "  certs-list|certs-clean"
	@echo "  db-backup           - backup VACUUM INTO (para $(DB_OUTDIR))"
	@echo "  db-vacuum|db-integrity"
	@echo "  db-export           - exporta tabela CSV (var: TABLE)"
	@echo "  db-search           - busca FTS (vars: QUERY, LIMIT)"
	@echo "  compose-prod-up     - sobe prod (proxy HTTPS + app)"
	@echo "  compose-prod-down   - derruba prod"
	@echo "  compose-dev-up      - sobe dev (hot-reload local)"
	@echo "  compose-dev-down    - derruba dev"
	@echo "  compose-logs        - tail logs dos serviços principais"
	@echo "  lint|test           - utilitários (stubs)"

# =========================
# Ambiente / deps
# =========================
.PHONY: venv
venv:
	python -m venv venv

.PHONY: install
install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "✅ Dependências instaladas. Ative o venv com:"
	@echo "   $(ACTIVATE)"

# =========================
# Execução local
# =========================
.PHONY: run
run:
	@echo "▶️  Flask na porta $(PORT)"
	@$(PY) server.py

.PHONY: run-ngrok
run-ngrok:
	@echo "🌐 Subindo Flask + ngrok (porta $(PORT))"
	@$(PY) server.py &
	@$(SLEEP)
	@$(PY) tools/ngrok_runner.py

.PHONY: health
health:
	@$(CURL) http://localhost:$(PORT)/health | python -m json.tool

.PHONY: metrics
metrics:
	@$(CURL) http://localhost:$(PORT)/metrics

.PHONY: index index-status
index:
python -m meu_app.services.pdf_indexer build --src $(PDF_SRC_DIR) --out $(RAG_INDEX_PATH) --model $(EMBED_MODEL)

index-status:
python -m meu_app.services.pdf_indexer status --out $(RAG_INDEX_PATH)

# =========================
# Admin endpoints (token)
# =========================
.PHONY: update-index
update-index:
	@echo "🔄 /update-index"
	@$(CURL) -X POST "http://localhost:$(PORT)/update-index" \
	  -H "X-API-Key: $(ADMIN_API_KEY)" | python -m json.tool || true

.PHONY: rebuild-index
rebuild-index:
	@echo "🧱 /rebuild-index"
	@$(CURL) -X POST "http://localhost:$(PORT)/rebuild-index" \
	  -H "X-API-Key: $(ADMIN_API_KEY)" | python -m json.tool || true

.PHONY: webhook-config
webhook-config:
	@echo "🔔 /zapi/configure-webhooks"
	@$(CURL) -X POST "http://localhost:$(PORT)/zapi/configure-webhooks" \
	  -H "X-API-Key: $(ADMIN_API_KEY)" -H "Content-Type: application/json" \
	  -d '{"received_url":"https://$(DOMAIN)/zapi/webhook/received"}' | python -m json.tool || true

# =========================
# Certificados
# =========================
.PHONY: certs-dev
certs-dev:
	@bash scripts/certs_dev.sh --domain $(DOMAIN)

.PHONY: certs-install
certs-install:
	@if [ -z "$(CERT)" ] || [ -z "$(KEY)" ]; then \
	  echo "Uso: make certs-install DOMAIN=seu.dominio CERT=/caminho/fullchain.pem KEY=/caminho/privkey.pem"; exit 1; \
	fi
	@bash scripts/certs_install_existing.sh --name $(DOMAIN) --cert $(CERT) --key $(KEY)

.PHONY: certs-list
certs-list:
	@ls -l data/certs || true

.PHONY: certs-clean
certs-clean:
	@rm -f data/certs/*.crt data/certs/*.key
	@echo 'limpo data/certs (exceto dhparam.pem/.gitkeep)'

# =========================
# Banco de dados (scripts/db_admin.py)
# =========================
.PHONY: db-backup
db-backup:
	@$(PY) scripts/db_admin.py backup --outdir $(DB_OUTDIR)

.PHONY: db-vacuum
db-vacuum:
	@$(PY) scripts/db_admin.py vacuum

.PHONY: db-integrity
db-integrity:
	@$(PY) scripts/db_admin.py integrity

.PHONY: db-export
db-export:
	@if [ -z "$(TABLE)" ]; then echo "Uso: make db-export TABLE=mensagens"; exit 1; fi
	@$(PY) scripts/db_admin.py export --table $(TABLE) --outdir $(DB_OUTDIR)

.PHONY: db-search
db-search:
	@if [ -z "$(QUERY)" ]; then echo "Uso: make db-search QUERY='multa NEAR abusiva' [LIMIT=20]"; exit 1; fi
	@$(PY) scripts/db_admin.py search "$(QUERY)" --limit $(LIMIT)

# =========================
# Docker / Compose
# =========================
.PHONY: compose-prod-up
compose-prod-up:
	$(COMPOSE) --profile prod --profile extras up -d --build

.PHONY: compose-prod-down
compose-prod-down:
	$(COMPOSE) --profile prod --profile extras down

.PHONY: compose-dev-up
compose-dev-up:
	$(COMPOSE) --profile dev up -d --build

.PHONY: compose-dev-down
compose-dev-down:
	$(COMPOSE) --profile dev down

.PHONY: compose-logs
compose-logs:
	$(COMPOSE) logs -f app app-dev reverse-proxy acme-companion || true

# =========================
# Qualidade (stubs)
# =========================
.PHONY: lint
lint:
	@echo "👉 Ative ruff em requirements.txt (seção dev) e rode:"
	@echo "ruff check ."

.PHONY: test
test:
	@echo "👉 Ative pytest em requirements.txt e rode:"
	@echo "pytest -q"
