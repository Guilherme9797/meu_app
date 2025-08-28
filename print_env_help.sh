#!/usr/bin/env bash
# scripts/print_env_help.sh
set -Eeuo pipefail

# ---------- cores ----------
if [[ -t 1 ]]; then
  GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; CYAN="\033[36m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"
else
  GREEN=""; YELLOW=""; RED=""; CYAN=""; BOLD=""; DIM=""; RESET=""
fi

ok()   { echo -e "${GREEN}✔${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
err()  { echo -e "${RED}✖${RESET} $*"; }
sec()  { echo -e "\n${BOLD}$*${RESET}"; }
kv()   { printf "  %s%-28s%s : %s\n" "${DIM}" "$1" "${RESET}" "$2"; }

mask() {
  local v="${1:-}"; [[ -z "$v" ]] && { echo ""; return; }
  local len=${#v}
  if (( len <= 6 )); then echo "***"; else echo "${v:0:3}***${v: -2}"; fi
}

DOTENV="${1:-.env}"
[[ -f "$DOTENV" ]] && { sec "Carregando ${DOTENV}"; set -a; source "$DOTENV"; set +a; } || warn "Arquivo ${DOTENV} não encontrado (ok)."

# Corrige/avisa sobre typos comuns
[[ -n "${NGROG_PROTO:-}" ]] && warn "Variável 'NGROG_PROTO' detectada. Provável typo → use 'NGROK_PROTO'."

# ---------- obrigatórias ----------
MISSING=0
req() {
  local name="$1" ; local val="${!name:-}"
  if [[ -z "$val" ]]; then err "$name não definido"; MISSING=1; else ok "$name definido"; fi
}

sec "Obrigatórias"
req OPENAI_API_KEY
req ADMIN_API_KEY

# ---------- grupos ----------
sec "Core da aplicação"
kv PORT                "${PORT:-5000}"
kv APP_DB_PATH         "${APP_DB_PATH:-data/app.db}"
kv INDEX_DIR           "${INDEX_DIR:-$(pwd)/index/faiss_index}"

sec "OpenAI"
kv OPENAI_MODEL        "${OPENAI_MODEL:-gpt-4o-mini}"
kv OPENAI_API_KEY      "$(mask "${OPENAI_API_KEY:-}")"

sec "Tavily (opcional)"
kv TAVILY_API_KEY      "$(mask "${TAVILY_API_KEY:-}")"

sec "Z-API (WhatsApp)"
kv ZAPI_INSTANCE_ID    "$(mask "${ZAPI_INSTANCE_ID:-}")"
kv ZAPI_TOKEN          "$(mask "${ZAPI_TOKEN:-}")"
kv ZAPI_BASE_URL       "${ZAPI_BASE_URL:-https://api.z-api.io}"
kv ZAPI_WEBHOOK_RECEIVED_URL "${ZAPI_WEBHOOK_RECEIVED_URL:-}"

sec "ngrok (opcional)"
kv NGROK_AUTHTOKEN     "$(mask "${NGROK_AUTHTOKEN:-}")"
kv NGROK_DOMAIN        "${NGROK_DOMAIN:-}"
kv NGROK_REGION        "${NGROK_REGION:-sa}"
kv NGROK_PROTO         "${NGROK_PROTO:-http}"
kv NGROK_EDGE_PATH     "${NGROK_EDGE_PATH:-}"

sec "CORS (opcional)"
kv ALLOWED_ORIGINS     "${ALLOWED_ORIGINS:-}"

sec "Rate limiting (opcional)"
kv RATE_LIMIT_DEFAULT  "${RATE_LIMIT_DEFAULT:-60 per minute}"
kv RATE_LIMIT_ADMIN    "${RATE_LIMIT_ADMIN:-10 per minute}"
kv RATE_LIMIT_WEBHOOK  "${RATE_LIMIT_WEBHOOK:-60 per minute}"
kv RATELIMIT_STORAGE_URI "${RATELIMIT_STORAGE_URI:-memory://}"

sec "Produção (HTTPS via docker-compose)"
kv DOMAIN              "${DOMAIN:-}"
kv LETSENCRYPT_EMAIL   "${LETSENCRYPT_EMAIL:-}"

# ---------- dicas ----------
sec "Dicas rápidas"
echo -e "• Ative o venv e instale dependências:"
echo -e "  ${CYAN}python -m venv venv && . venv/bin/activate && pip install -r requirements.txt${RESET}"
echo -e "• Rodar o servidor local:"
echo -e "  ${CYAN}python server.py${RESET}"
echo -e "• Subir com ngrok (2 terminais):"
echo -e "  ${CYAN}python server.py${RESET}  # terminal 1"
echo -e "  ${CYAN}python tools/ngrok_runner.py${RESET}  # terminal 2"
echo -e "• Testar saúde:"
echo -e "  ${CYAN}curl -s http://localhost:${PORT:-5000}/health | jq${RESET}"
echo -e "• Atualizar índice (admin):"
echo -e "  ${CYAN}curl -s -X POST http://localhost:${PORT:-5000}/update-index -H \"X-API-Key: \$ADMIN_API_KEY\" | jq${RESET}"
echo -e "• Configurar webhook na Z-API (produção):"
echo -e "  ${CYAN}curl -s -X POST https://\${DOMAIN}/zapi/configure-webhooks -H \"X-API-Key: \$ADMIN_API_KEY\" -H 'Content-Type: application/json' -d '{\"received_url\":\"https://\${DOMAIN}/zapi/webhook/received\"}' | jq${RESET}"

sec "Docker / Compose"
echo -e "• Dev:"
echo -e "  ${CYAN}docker compose --profile dev up -d --build${RESET}  → http://localhost:5000/health"
echo -e "• Prod (HTTPS + Redis opcional):"
echo -e "  ${CYAN}docker compose --profile prod --profile extras up -d --build${RESET}  → https://\${DOMAIN}/health"

# ---------- avisos condicionais ----------
if [[ -z "${ZAPI_INSTANCE_ID:-}" || -z "${ZAPI_TOKEN:-}" ]]; then
  warn "Credenciais Z-API ausentes — integração WhatsApp ficará desabilitada."
fi
if [[ -z "${NGROK_AUTHTOKEN:-}" && -z "${DOMAIN:-}" ]]; then
  warn "Sem NGROK_AUTHTOKEN e sem DOMAIN: você não terá URL pública para webhooks (apenas local)."
fi

# ---------- saída/retorno ----------
echo ""
if (( MISSING )); then
  err "Algumas variáveis obrigatórias estão faltando. Ex.:"
  echo "  export OPENAI_API_KEY=xxxxxxxx"
  echo "  export ADMIN_API_KEY=um_token_secreto_forte"
  exit 1
else
  ok "Ambiente parece OK. Boa!"
fi
