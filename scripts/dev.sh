#!/usr/bin/env bash
#
# Run TurfApp locally: infrastructure, Django, Celery and Next.js in one terminal.
#
#   ./scripts/dev.sh                 everything
#   ./scripts/dev.sh --no-worker     skip Celery (nothing schedules work until Phase 03)
#   ./scripts/dev.sh --backend       API only
#   ./scripts/dev.sh --help          all options
#
# Ctrl+C stops every process it started. Containers are left running on purpose —
# `docker compose down` when you actually want them gone.
#
# Written for bash 3.2, the version macOS ships: no associative arrays, no `wait -n`.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
REQUIRED_NODE_MAJOR=24

RUN_INFRA=1
RUN_BACKEND=1
RUN_WORKER=1
RUN_FRONTEND=1
RUN_MIGRATE=1
CLERK_KEY_OK=1

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_CYAN=$'\033[36m'
else
  C_RESET=''; C_DIM=''; C_BOLD=''
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_MAGENTA=''; C_CYAN=''
fi

step() { printf '%s==>%s %s\n' "$C_BOLD$C_BLUE" "$C_RESET" "$*"; }
ok() { printf '%s  ok%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
fail() { printf '%sfail%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
die() { fail "$*"; exit 1; }

usage() {
  cat <<EOF
${C_BOLD}TurfApp dev runner${C_RESET}

Usage: ./scripts/dev.sh [options]

Options:
  --backend            Django only (implies --no-worker --no-frontend)
  --frontend           Next.js only (implies --no-infra --no-backend --no-worker)
  --no-infra           Do not touch Docker; assume Postgres and Redis are up
  --no-backend         Do not start Django
  --no-worker          Do not start the Celery worker and beat
  --no-frontend        Do not start Next.js
  --no-migrate         Skip 'manage.py migrate' on startup
  -h, --help           Show this message

Environment:
  BACKEND_PORT         Django port (default 8000)
  FRONTEND_PORT        Next.js port (default 3000)
  NO_COLOR             Disable coloured output

Logs are mirrored to .logs/<service>.log while the script runs.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --backend) RUN_WORKER=0; RUN_FRONTEND=0 ;;
    --frontend) RUN_INFRA=0; RUN_BACKEND=0; RUN_WORKER=0; RUN_MIGRATE=0 ;;
    --no-infra) RUN_INFRA=0 ;;
    --no-backend) RUN_BACKEND=0 ;;
    --no-worker) RUN_WORKER=0 ;;
    --no-frontend) RUN_FRONTEND=0 ;;
    --no-migrate) RUN_MIGRATE=0 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown option: $1"; echo; usage; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Process supervision
# ---------------------------------------------------------------------------
PIDS=()
NAMES=()
SHUTTING_DOWN=0

# Killing the subshell alone orphans the server it spawned, so walk the tree.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null
}

cleanup() {
  [ "$SHUTTING_DOWN" -eq 1 ] && return
  SHUTTING_DOWN=1
  trap '' INT TERM

  if [ ${#PIDS[@]} -gt 0 ]; then
    printf '\n'
    step "Stopping services"
    local i
    for i in "${!PIDS[@]}"; do
      if kill -0 "${PIDS[$i]}" 2>/dev/null; then
        kill_tree "${PIDS[$i]}"
        ok "stopped ${NAMES[$i]}"
      fi
    done
    wait 2>/dev/null
  fi

  if [ "$RUN_INFRA" -eq 1 ]; then
    printf '%sPostgres and Redis are still running. `docker compose down` to stop them.%s\n' \
      "$C_DIM" "$C_RESET"
  fi
}
trap cleanup EXIT INT TERM

# Run a service in the background, prefixing each line and mirroring it to a log file.
# awk (not sed) because it flushes per line portably, so output is not held in a buffer.
start_service() {
  local name="$1" color="$2" dir="$3"
  shift 3

  local logfile="$LOG_DIR/$name.log"
  : > "$logfile"

  (
    cd "$dir" || exit 1
    "$@" 2>&1 | awk -v p="${color}[${name}]${C_RESET} " -v f="$logfile" \
      '{ print p $0; fflush(); print > f; fflush(f) }'
  ) &

  PIDS+=($!)
  NAMES+=("$name")
}

wait_for_http() {
  local url="$1" label="$2" tries="${3:-60}" i=1
  while [ "$i" -le "$tries" ]; do
    if curl -fsS -o /dev/null --max-time 2 "$url" 2>/dev/null; then
      ok "$label is up"
      return 0
    fi
    # A service that died will never answer; stop waiting on it.
    if [ "$SHUTTING_DOWN" -eq 1 ]; then return 1; fi
    sleep 1
    i=$((i + 1))
  done
  warn "$label did not answer at $url after ${tries}s (see .logs/)"
  return 1
}

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
step "Checking prerequisites"

if [ "$RUN_BACKEND" -eq 1 ] || [ "$RUN_MIGRATE" -eq 1 ] || [ "$RUN_WORKER" -eq 1 ]; then
  command -v uv >/dev/null 2>&1 || die "uv is not installed. Run: brew install uv"

  # GeoDjango loads GEOS/GDAL through ctypes, so importing any model with a PointField
  # fails without the native libraries — even though PostGIS itself runs in Docker.
  if [ "$(uname -s)" = "Darwin" ]; then
    gdal_path="${GDAL_LIBRARY_PATH:-/opt/homebrew/lib/libgdal.dylib}"
    geos_path="${GEOS_LIBRARY_PATH:-/opt/homebrew/lib/libgeos_c.dylib}"
    if [ ! -e "$gdal_path" ] || [ ! -e "$geos_path" ]; then
      die "GDAL/GEOS not found ($gdal_path). Run: brew install gdal"
    fi
  fi

  [ -f "$ROOT_DIR/backend/.env" ] || {
    warn "backend/.env is missing; creating it from .env.example"
    cp "$ROOT_DIR/backend/.env.example" "$ROOT_DIR/backend/.env"
  }
fi

if [ "$RUN_FRONTEND" -eq 1 ]; then
  command -v node >/dev/null 2>&1 || die "node is not installed. Run: brew install node@24"

  node_major="$(node -v | sed 's/^v\([0-9]*\).*/\1/')"
  if [ "$node_major" -lt "$REQUIRED_NODE_MAJOR" ]; then
    warn "Node $(node -v) is older than the required v${REQUIRED_NODE_MAJOR}."
    warn "Run: brew install node@24 && brew link --overwrite node@24"
  fi

  [ -d "$ROOT_DIR/frontend/node_modules" ] || die \
    "frontend/node_modules is missing. Run: cd frontend && npm install"

  [ -f "$ROOT_DIR/frontend/.env.local" ] || {
    warn "frontend/.env.local is missing; creating it from .env.local.example"
    cp "$ROOT_DIR/frontend/.env.local.example" "$ROOT_DIR/frontend/.env.local"
  }

  # Clerk refuses to initialise without a publishable key, so the app would 500 on
  # every page. Worth saying plainly up front rather than letting it look like a bug.
  if ! grep -qE '^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_' "$ROOT_DIR/frontend/.env.local"; then
    CLERK_KEY_OK=0
    warn "No Clerk publishable key in frontend/.env.local — every page will return 500."
    warn "Add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY from"
    warn "https://dashboard.clerk.com -> API keys (see README.md). The API works regardless."
  fi
fi

if [ "$RUN_BACKEND" -eq 1 ] && port_in_use "$BACKEND_PORT"; then
  die "Port $BACKEND_PORT is already in use. Stop that process or set BACKEND_PORT."
fi
if [ "$RUN_FRONTEND" -eq 1 ] && port_in_use "$FRONTEND_PORT"; then
  die "Port $FRONTEND_PORT is already in use. Stop that process or set FRONTEND_PORT."
fi

ok "prerequisites satisfied"

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------
if [ "$RUN_INFRA" -eq 1 ]; then
  step "Starting Postgres and Redis"

  if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null 2>&1; then
      warn "Docker daemon is not running; starting Colima (this takes a moment)"
      colima start >/dev/null 2>&1 || die "colima start failed. Run it manually to see why."
    else
      die "Docker daemon is not running. Start Docker Desktop (or 'colima start')."
    fi
  fi

  (cd "$ROOT_DIR" && docker compose up -d) >/dev/null 2>&1 \
    || die "docker compose up failed. Run it directly to see the error."

  # Migrations against a half-ready Postgres fail confusingly, so wait for healthy.
  [ -t 1 ] && printf '%s  ..%s waiting for containers to report healthy' "$C_DIM" "$C_RESET"
  i=1
  while [ "$i" -le 60 ]; do
    states="$(cd "$ROOT_DIR" && docker compose ps --format '{{.Service}}:{{.Health}}' 2>/dev/null)"
    unhealthy="$(printf '%s\n' "$states" | grep -cv ':healthy$' 2>/dev/null)"
    if [ -n "$states" ] && [ "$unhealthy" -eq 0 ]; then
      [ -t 1 ] && printf '\r\033[K'
      ok "postgres and redis are healthy"
      break
    fi
    [ -t 1 ] && printf '.'
    sleep 1
    i=$((i + 1))
  done
  if [ "$i" -gt 60 ]; then
    [ -t 1 ] && printf '\r\033[K'
    die "Containers never became healthy. Check: docker compose ps && docker compose logs"
  fi
fi

# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
if [ "$RUN_MIGRATE" -eq 1 ]; then
  step "Applying migrations"
  if (cd "$ROOT_DIR/backend" && uv run python manage.py migrate --noinput) > "$LOG_DIR/migrate.log" 2>&1; then
    applied="$(grep -c '  Applying' "$LOG_DIR/migrate.log" 2>/dev/null)"
    if [ "${applied:-0}" -gt 0 ]; then
      ok "applied $applied migration(s)"
    else
      ok "database is up to date"
    fi
  else
    tail -20 "$LOG_DIR/migrate.log" >&2
    die "Migrations failed (full output in .logs/migrate.log)"
  fi
fi

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
step "Starting services"

if [ "$RUN_BACKEND" -eq 1 ]; then
  start_service "api" "$C_CYAN" "$ROOT_DIR/backend" \
    uv run python manage.py runserver "127.0.0.1:$BACKEND_PORT"
fi

if [ "$RUN_WORKER" -eq 1 ]; then
  # -B runs beat in-process: fine for development, separate processes in production.
  start_service "worker" "$C_MAGENTA" "$ROOT_DIR/backend" \
    uv run celery -A config worker -B -l info --concurrency=2
fi

if [ "$RUN_FRONTEND" -eq 1 ]; then
  start_service "web" "$C_GREEN" "$ROOT_DIR/frontend" \
    npm run dev -- --port "$FRONTEND_PORT"
fi

[ ${#PIDS[@]} -eq 0 ] && die "Nothing to run with those options."

# ---------------------------------------------------------------------------
# Readiness summary
# ---------------------------------------------------------------------------
if [ "$RUN_BACKEND" -eq 1 ]; then
  wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/v1/health" "API"
fi
if [ "$RUN_FRONTEND" -eq 1 ]; then
  if [ "$CLERK_KEY_OK" -eq 1 ]; then
    # Next's dev server accepts connections before it has compiled a page, so allow
    # time for the first compile rather than reporting a false failure.
    wait_for_http "http://127.0.0.1:$FRONTEND_PORT/" "Web" 90
  else
    # No point waiting out the full timeout for pages we already know will 500.
    wait_for_http "http://127.0.0.1:$FRONTEND_PORT/" "Web" 10 \
      || warn "Web is listening but every page errors until the Clerk keys are set."
  fi
fi

printf '\n%s%sTurfApp is running%s\n' "$C_BOLD" "$C_GREEN" "$C_RESET"
[ "$RUN_FRONTEND" -eq 1 ] && printf '  app      http://localhost:%s\n' "$FRONTEND_PORT"
if [ "$RUN_BACKEND" -eq 1 ]; then
  printf '  health   http://127.0.0.1:%s/api/v1/health\n' "$BACKEND_PORT"
  printf '  docs     http://127.0.0.1:%s/api/v1/docs/\n' "$BACKEND_PORT"
  printf '  admin    http://127.0.0.1:%s/admin/\n' "$BACKEND_PORT"
fi
printf '%s  logs in .logs/ · Ctrl+C to stop%s\n\n' "$C_DIM" "$C_RESET"

# ---------------------------------------------------------------------------
# Supervise until Ctrl+C, or until something dies
# ---------------------------------------------------------------------------
# bash 3.2 has no `wait -n`, so poll the children instead.
while true; do
  # The signal trap runs between commands, so re-check before judging a dead child:
  # after Ctrl+C the children are *meant* to be gone.
  [ "$SHUTTING_DOWN" -eq 1 ] && exit 0
  for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
      [ "$SHUTTING_DOWN" -eq 1 ] && exit 0
      fail "${NAMES[$i]} exited unexpectedly — see .logs/${NAMES[$i]}.log"
      exit 1
    fi
  done
  sleep 1
done
