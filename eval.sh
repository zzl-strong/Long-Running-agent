#!/bin/bash
# Benchmark evaluation — follows the original NL2RepoBench approach:
# 0. Clean up previous eval container
# 1. Read test_files.json → clean agent workspace
# 2. Pull golden test image if not local
# 3. docker build FROM test-image + COPY workspace /workspace
# 4. docker run the built image with the test commands
# 5. Parse pytest results, compute score, save result
#
# Usage: ./eval.sh <project-dir> <task-name>
# Example: ./eval.sh bench-decouple decouple
#
# Files are read from: <script-dir>/NL2RepoBench-main/test_files/<task-name>/

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <project-dir> <task-name>"
  echo "Example: $0 bench-decouple decouple"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$1"
TASK="$2"
TEST_BASE="${SCRIPT_DIR}/NL2RepoBench-main/test_files/${TASK}"
WORKSPACE="$(realpath "${PROJECT_DIR}/workspace")"
TEST_IMAGE="ghcr.nju.edu.cn/multimodal-art-projection/nl2repobench/${TASK}:1.0"
TEMP_IMAGE="eval-${TASK}:tmp"
LOG_FILE="$(realpath "${PROJECT_DIR}")/eval.log"
RESULT_FILE="$(realpath "${PROJECT_DIR}")/eval-result.json"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

# ── Pre-checks ───────────────────────────────────────────────────────
if [ ! -d "$WORKSPACE" ]; then
  echo -e "${RED}❌ Workspace not found: $WORKSPACE${NC}"
  exit 1
fi
for f in test_commands.json test_files.json; do
  if [ ! -f "${TEST_BASE}/$f" ]; then
    echo -e "${RED}❌ $f not found at ${TEST_BASE}${NC}"
    exit 1
  fi
done

# Read expected test case count (optional)
EXPECTED_COUNT=""
if [ -f "${TEST_BASE}/test_case_count.txt" ]; then
  EXPECTED_COUNT=$(cat "${TEST_BASE}/test_case_count.txt" | tr -d '[:space:]')
fi

echo "============================================"
echo "  Evaluating: $TASK"
echo "  Project:    $PROJECT_DIR"
echo "============================================"

# ── Step 0: Clean up any previous eval container ─────────────────────
docker rm -f "eval-${TASK}" 2>/dev/null || true

# ── Step 1: Stage workspace files (copy to temp dir, never delete originals) ──
echo ""
echo "[1/4] Staging workspace (temp dir, host files untouched)..."
STAGING_DIR=$(mktemp -d)
trap "rm -rf '$STAGING_DIR'" EXIT

# Copy workspace to staging dir (preserving all host files)
cp -a "$WORKSPACE" "$STAGING_DIR/workspace"

# Read exclusions from test_files.json
TEST_FILES_TO_EXCLUDE=$(python3 -c "import json; print('\n'.join(json.load(open('${TEST_BASE}/test_files.json'))))")
while IFS= read -r f; do
  [ -z "$f" ] && continue
  target="$STAGING_DIR/workspace/$f"
  if [ -e "$target" ]; then
    rm -rf "$target"
    echo "  excluded from image: $f"
  fi
done <<< "$TEST_FILES_TO_EXCLUDE"

# Also remove common package files from staging only
rm -f "$STAGING_DIR"/workspace/setup.py "$STAGING_DIR"/workspace/setup.cfg \
      "$STAGING_DIR"/workspace/pyproject.toml \
      "$STAGING_DIR"/workspace/requirements*.txt "$STAGING_DIR"/workspace/pytest.ini \
      "$STAGING_DIR"/workspace/tox.ini "$STAGING_DIR"/workspace/poetry.lock \
      "$STAGING_DIR"/workspace/Pipfile* "$STAGING_DIR"/workspace/MANIFEST.in \
      "$STAGING_DIR"/workspace/environment.yml "$STAGING_DIR"/workspace/conda-env.yaml
rm -rf "$STAGING_DIR"/workspace/__pycache__
echo "  done"

# ── Ensure golden test image exists locally ──────────────────────────
echo ""
echo "[2/4] Ensuring test image..."
if ! docker image inspect "${TEST_IMAGE}" &>/dev/null; then
  echo "  📥 Pulling: ${TEST_IMAGE}"
  docker pull "${TEST_IMAGE}"
else
  echo "  ✅ Already local: ${TEST_IMAGE}"
fi

# ── Step 3: Build test image ────────────────────────────────────────
echo ""
echo "[3/4] Building evaluation image..."
echo "FROM ${TEST_IMAGE}
COPY workspace /workspace" | docker build -t "$TEMP_IMAGE" -f- "$STAGING_DIR" > /dev/null 2>&1
echo "  image: $TEMP_IMAGE"

# ── Step 4: Run test commands ────────────────────────────────────────
echo ""
echo "[4/4] Running tests..."
echo "  Commands:"
TEST_COMMANDS=$(python3 -c "
import json
cmds = json.load(open('${TEST_BASE}/test_commands.json'))
parts = []
for i, c in enumerate(cmds):
    parts.append(f'echo \"    [{i+1}/{len(cmds)}] \$ {c}\"')
    parts.append(c)
print(' && '.join(parts))
")

set +e
docker run --name "eval-${TASK}" "$TEMP_IMAGE" sh -c "$TEST_COMMANDS" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

# ── Step 5: Parse pytest results and save ────────────────────────────
echo ""
echo "[5/5] Parsing results..."

PYTEST_OUTPUT=$(cat "$LOG_FILE")

# Parse pytest summary line like: "= 45 passed, 2 failed, 3 errors in 12.34s ="
PASSED=0
FAILED=0
ERRORS=0
if echo "$PYTEST_OUTPUT" | grep -qP 'passed|failed|error'; then
  PASSED=$(echo "$PYTEST_OUTPUT" | grep -oP '\d+(?= passed)' | tail -1 | grep -oP '\d+' || echo 0)
  FAILED=$(echo "$PYTEST_OUTPUT" | grep -oP '\d+(?= failed)' | tail -1 | grep -oP '\d+' || echo 0)
  ERRORS=$(echo "$PYTEST_OUTPUT" | grep -oP '\d+(?= errors)' | tail -1 | grep -oP '\d+' || echo 0)
fi

# Compute score: passed / expected_count (or passed / (passed+failed+errors) if no expected)
if [ -n "$EXPECTED_COUNT" ] && [ "$EXPECTED_COUNT" -gt 0 ] 2>/dev/null; then
  SCORE=$(python3 -c "print(min($PASSED / $EXPECTED_COUNT, 1.0))")
  TOTAL_EXPECTED="$EXPECTED_COUNT"
else
  TOTAL=$((PASSED + FAILED + ERRORS))
  if [ "$TOTAL" -gt 0 ]; then
    SCORE=$(python3 -c "print($PASSED / $TOTAL)")
  else
    SCORE=0
  fi
  TOTAL_EXPECTED="N/A"
fi

# Determine status
if [ "$EXIT_CODE" -eq 0 ] && [ "$FAILED" -eq 0 ] && [ "$ERRORS" -eq 0 ]; then
  STATUS="passed"
  COLOR=$GREEN
elif [ "$EXIT_CODE" -ne 0 ]; then
  STATUS="error"
  COLOR=$RED
else
  STATUS="failed"
  COLOR=$YELLOW
fi

# Build result JSON
python3 -c "
import json
result = {
    'task': '$TASK',
    'project_dir': '$PROJECT_DIR',
    'timestamp': '$(date -Iseconds)',
    'status': '$STATUS',
    'exit_code': $EXIT_CODE,
    'score': $SCORE,
    'pytest_passed': $PASSED,
    'pytest_failed': $FAILED,
    'pytest_errors': $ERRORS,
    'total_expected': '$TOTAL_EXPECTED',
}
json.dump(result, open('$RESULT_FILE', 'w'), indent=2)
"

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo -e "  Result: ${COLOR}${STATUS}${NC}"
echo "  Score:  $(python3 -c "print(f'{${SCORE}*100:.1f}%')")"
echo "  Tests:  $PASSED passed, $FAILED failed, $ERRORS errors"
if [ -n "$EXPECTED_COUNT" ]; then
  echo "  Expected: $EXPECTED_COUNT total"
fi
echo "  Exit:   $EXIT_CODE"
echo "============================================"
echo ""
echo "Saved:"
echo "  Log:    $LOG_FILE"
echo "  Result: $RESULT_FILE"
echo ""

# ── Stop eval container (keep for inspection, not deleted) ──────────
echo "🛑 Stopping eval container: eval-${TASK}"
docker stop "eval-${TASK}" > /dev/null 2>&1 && echo "   ✅ Stopped" || echo "   (already stopped)"
echo ""
echo "Inspect / re-run with:"
echo "  docker start -ai eval-${TASK}"
echo "Clean up after done:"
echo "  docker rm eval-${TASK} && docker rmi $TEMP_IMAGE"
