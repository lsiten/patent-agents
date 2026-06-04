#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_DIR=$(mktemp -d)
cleanup() {
    if [ -d "$TMP_DIR/project" ]; then
        "$TMP_DIR/project/start.sh" stop all >/dev/null 2>&1 || true
    fi
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PROJECT="$TMP_DIR/project"
mkdir -p "$PROJECT/backend/venv/bin" "$PROJECT/frontend/node_modules" "$PROJECT/bin" "$PROJECT/logs"
cp "$ROOT/start.sh" "$PROJECT/start.sh"
chmod +x "$PROJECT/start.sh"
touch "$PROJECT/backend/venv/bin/activate" "$PROJECT/backend/venv/.deps_installed"

cat > "$PROJECT/backend/.env" <<'ENV'
ENVIRONMENT=development
PORT=8000
ENV
cat > "$PROJECT/backend/.env.testing" <<'ENV'
ENVIRONMENT=testing
PORT=8000
ENV
cat > "$PROJECT/backend/.env.production" <<'ENV'
ENVIRONMENT=production
PORT=10002
ENV
cat > "$PROJECT/frontend/.env.development" <<'ENV'
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV
cat > "$PROJECT/frontend/.env.production" <<'ENV'
NEXT_PUBLIC_API_URL=https://patent-api.lene.fun/api/v1
ENV

cat > "$PROJECT/bin/python" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "main.py" ]; then
    echo "${PATENT_AGENTS_ENV_FILE:-<missing>}" >> "$FAKE_LOG/backend_env_files.log"
    echo "backend $$ ${PATENT_AGENTS_ENV_FILE:-<missing>}" >> "$FAKE_LOG/processes.log"
    trap 'exit 0' TERM INT
    while true; do sleep 1; done
fi
exit 0
SH
chmod +x "$PROJECT/bin/python"
ln -s python "$PROJECT/bin/python3"

cat > "$PROJECT/bin/npx" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$FAKE_LOG/npx_commands.log"
if [ "${1:-}" = "next" ] && [ "${2:-}" = "build" ]; then
    exit 0
fi
if [ "${1:-}" = "next" ] && { [ "${2:-}" = "dev" ] || [ "${2:-}" = "start" ]; }; then
    echo "frontend $$ $*" >> "$FAKE_LOG/processes.log"
    trap 'exit 0' TERM INT
    while true; do sleep 1; done
fi
exit 0
SH
chmod +x "$PROJECT/bin/npx"

cat > "$PROJECT/bin/npm" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$PROJECT/bin/npm"

cat > "$PROJECT/bin/node" <<'SH'
#!/usr/bin/env bash
echo "v20.0.0"
SH
chmod +x "$PROJECT/bin/node"

cat > "$PROJECT/bin/lsof" <<'SH'
#!/usr/bin/env bash
exit 1
SH
chmod +x "$PROJECT/bin/lsof"

export PATH="$PROJECT/bin:$PATH"
export FAKE_LOG="$PROJECT/logs"

start_env() {
    local env=$1
    (cd "$PROJECT" && ./start.sh "$env" >"$PROJECT/logs/${env}.out" 2>"$PROJECT/logs/${env}.err") &
    STARTED_PID=$!
}

wait_for_file() {
    local file=$1
    local label=$2
    for _ in {1..50}; do
        [ -s "$file" ] && return 0
        sleep 0.1
    done
    echo "missing $label: $file" >&2
    echo "--- dev.out ---" >&2
    [ -f "$PROJECT/logs/dev.out" ] && cat "$PROJECT/logs/dev.out" >&2
    echo "--- dev.err ---" >&2
    [ -f "$PROJECT/logs/dev.err" ] && cat "$PROJECT/logs/dev.err" >&2
    echo "--- production.out ---" >&2
    [ -f "$PROJECT/logs/production.out" ] && cat "$PROJECT/logs/production.out" >&2
    echo "--- production.err ---" >&2
    [ -f "$PROJECT/logs/production.err" ] && cat "$PROJECT/logs/production.err" >&2
    return 1
}

assert_alive() {
    local pid=$1
    local label=$2
    kill -0 "$pid" 2>/dev/null || { echo "$label should be alive" >&2; exit 1; }
}

assert_dead() {
    local pid=$1
    local label=$2
    for _ in {1..30}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    echo "$label should be stopped" >&2
    exit 1
}

start_env dev
DEV_WRAPPER=$STARTED_PID
start_env production
PROD_WRAPPER=$STARTED_PID

wait_for_file "$PROJECT/.runtime/start.sh/dev/backend.pid" "dev backend pid"
wait_for_file "$PROJECT/.runtime/start.sh/dev/frontend.pid" "dev frontend pid"
wait_for_file "$PROJECT/.runtime/start.sh/production/backend.pid" "production backend pid"
wait_for_file "$PROJECT/.runtime/start.sh/production/frontend.pid" "production frontend pid"

DEV_BACKEND=$(cat "$PROJECT/.runtime/start.sh/dev/backend.pid")
DEV_FRONTEND=$(cat "$PROJECT/.runtime/start.sh/dev/frontend.pid")
PROD_BACKEND=$(cat "$PROJECT/.runtime/start.sh/production/backend.pid")
PROD_FRONTEND=$(cat "$PROJECT/.runtime/start.sh/production/frontend.pid")

assert_alive "$DEV_BACKEND" "dev backend"
assert_alive "$DEV_FRONTEND" "dev frontend"
assert_alive "$PROD_BACKEND" "production backend"
assert_alive "$PROD_FRONTEND" "production frontend"

(cd "$PROJECT" && ./start.sh stop dev >/dev/null)
assert_dead "$DEV_BACKEND" "dev backend"
assert_dead "$DEV_FRONTEND" "dev frontend"
assert_alive "$PROD_BACKEND" "production backend after stop dev"
assert_alive "$PROD_FRONTEND" "production frontend after stop dev"

start_env dev
DEV_WRAPPER=$STARTED_PID
wait_for_file "$PROJECT/.runtime/start.sh/dev/backend.pid" "restarted dev backend pid"
wait_for_file "$PROJECT/.runtime/start.sh/dev/frontend.pid" "restarted dev frontend pid"
DEV_BACKEND=$(cat "$PROJECT/.runtime/start.sh/dev/backend.pid")
DEV_FRONTEND=$(cat "$PROJECT/.runtime/start.sh/dev/frontend.pid")

(cd "$PROJECT" && ./start.sh stop production >/dev/null)
assert_dead "$PROD_BACKEND" "production backend"
assert_dead "$PROD_FRONTEND" "production frontend"
assert_alive "$DEV_BACKEND" "dev backend after stop production"
assert_alive "$DEV_FRONTEND" "dev frontend after stop production"

if [ -e "$PROJECT/frontend/.env.local" ]; then
    echo "frontend/.env.local must not be created" >&2
    exit 1
fi

grep -F "$PROJECT/backend/.env" "$PROJECT/logs/backend_env_files.log" >/dev/null
grep -F "$PROJECT/backend/.env.production" "$PROJECT/logs/backend_env_files.log" >/dev/null
grep -F "next dev -p 3000" "$PROJECT/logs/npx_commands.log" >/dev/null
grep -F "next build" "$PROJECT/logs/npx_commands.log" >/dev/null
grep -F "next start -p 10001" "$PROJECT/logs/npx_commands.log" >/dev/null

(cd "$PROJECT" && ./start.sh stop all >/dev/null)
wait "$DEV_WRAPPER" 2>/dev/null || true
wait "$PROD_WRAPPER" 2>/dev/null || true

echo "PASS start.sh dev/production isolation"
