#!/bin/bash
# Usage: ./run_bench_task_no_verify.sh <project_name> [--resume]
#
# Same as run_bench_task.sh, but with verification DISABLED — the model's
# self-reported completion status is trusted without running Tier-1/Tier-2
# checks. Project directory is suffixed with "-no-verify" to distinguish
# from verified runs.
#
# Example:
#   ./run_bench_task_no_verify.sh decouple         # start fresh, no verify
#   ./run_bench_task_no_verify.sh decouple --resume # resume interrupted
#
# Directory naming:
#   bench-<project_name>-no-verify/   (vs bench-<project_name>/ for verified)
#   bench-runtime-<project_name>-no-verify  (Docker container)

set -euo pipefail

# ── Determine base directory (where this script lives) ───────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <project_name> [--resume]"
  echo "Example:"
  echo "  $(basename "$0") decouple          # start fresh"
  echo "  $(basename "$0") decouple --resume  # resume interrupted"
  echo ""
  echo "Available projects:"
  ls "${SCRIPT_DIR}/NL2RepoBench-main/test_files/" 2>/dev/null || echo "  (NL2RepoBench-main/test_files/ not found)"
  exit 1
fi

PROJECT_NAME="$1"
MODE="${2:-}"  # --resume or empty
BASE_DIR="${SCRIPT_DIR}"
BENCH_DIR="${BASE_DIR}/bench-${PROJECT_NAME}-no-verify"
WORKSPACE_DIR="${BENCH_DIR}/workspace"
CONTAINER_NAME="bench-runtime-${PROJECT_NAME}-no-verify"
RUNTIME_IMAGE="ghcr.nju.edu.cn/all-hands-ai/runtime:0.56-nikolaik"
START_MD="${BASE_DIR}/NL2RepoBench-main/test_files/${PROJECT_NAME}/start.md"
AGENT_DIR="${BASE_DIR}/my_agent"

# ── Check prerequisites ──────────────────────────────────────────────
if [ ! -f "${START_MD}" ]; then
  echo "❌ start.md not found at ${START_MD}"
  echo "   Available projects:"
  ls "${BASE_DIR}/NL2RepoBench-main/test_files/"
  exit 1
fi

if [ ! -d "${AGENT_DIR}" ]; then
  echo "❌ my_agent not found at ${AGENT_DIR}"
  echo "   Expected: ${AGENT_DIR}"
  exit 1
fi

# ── Banner ────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ⚠️  VERIFICATION DISABLED"
echo "  Model's self-reported status will be trusted."
echo "  Project directory: ${BENCH_DIR}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: create project directory structure (always) ──────────────
echo "📁 Setting up project directory: ${BENCH_DIR}"
mkdir -p "${WORKSPACE_DIR}"
mkdir -p "${BENCH_DIR}/.agent/memory/handoffs"
mkdir -p "${BENCH_DIR}/.agent/skills"
mkdir -p "${BENCH_DIR}/logs"

# ── Step 2: create config.yaml (if not exists, or fresh start) ──────
if [ ! -f "${BENCH_DIR}/config.yaml" ] || [ "${MODE}" != "--resume" ]; then
  echo "⚙️  Creating config.yaml (runtime_container: ${CONTAINER_NAME}, verification: DISABLED)"
  cat > "${BENCH_DIR}/config.yaml" << CONFIGEOF
docker:
  runtime_container: "${CONTAINER_NAME}"
  test_image_prefix: "ghcr.nju.edu.cn/multimodal-art-projection/nl2repobench"

verification:
  enabled: false
CONFIGEOF
else
  echo "⚙️  Keeping existing config.yaml"
fi

# ── Ensure runtime image exists locally ──────────────────────────────
if ! docker image inspect "${RUNTIME_IMAGE}" &>/dev/null; then
  echo "📥 Pulling runtime image: ${RUNTIME_IMAGE}"
  docker pull "${RUNTIME_IMAGE}"
fi

# ── Step 3: restart runtime container ────────────────────────────────
if [ "${MODE}" == "--resume" ]; then
  # Resume: reuse existing container if possible, never delete
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "🐳 Container ${CONTAINER_NAME} already running, reusing it"
  elif docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "🐳 Container ${CONTAINER_NAME} exists but stopped, restarting it"
    docker start "${CONTAINER_NAME}"
  else
    echo "🐳 Container ${CONTAINER_NAME} not found, creating new one"
    docker run -d --name "${CONTAINER_NAME}" \
      -v "${BENCH_DIR}:/workspace" \
      "${RUNTIME_IMAGE}" \
      tail -f /dev/null
    echo "   ✅ Container ${CONTAINER_NAME} started"
  fi
else
  # Fresh start: always remove and recreate
  echo "🐳 (Re)starting runtime container: ${CONTAINER_NAME}"
  docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
  docker run -d --name "${CONTAINER_NAME}" \
    -v "${BENCH_DIR}:/workspace" \
    "${RUNTIME_IMAGE}" \
    tail -f /dev/null
  echo "   ✅ Container ${CONTAINER_NAME} started"
fi

# ── Step 4: launch my_agent, then stop runtime container ─────────────
if [ "${MODE}" == "--resume" ]; then
  echo "🚀 Resuming my_agent (no-verify mode) for task: ${PROJECT_NAME}"
  echo "   Project: ${BENCH_DIR}"
  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "  ⚠️  VERIFICATION DISABLED — trusting model self-report"
  echo "  Resuming agent. Previous workspace preserved at:"
  echo "    ${WORKSPACE_DIR}"
  echo "  Bash commands run inside container:"
  echo "    ${CONTAINER_NAME}"
  echo "═══════════════════════════════════════════════════════════════"
  echo ""

  cd "${AGENT_DIR}"

  # shellcheck disable=SC2086
  python -m harness.cli resume \
    --task "${PROJECT_NAME}" \
    --project "${BENCH_DIR}"
else
  echo "🚀 Launching my_agent (no-verify mode) for task: ${PROJECT_NAME}"
  echo "   Spec: ${START_MD}"
  echo "   Project: ${BENCH_DIR}"
  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "  ⚠️  VERIFICATION DISABLED — trusting model self-report"
  echo "  Agent started. Code will be written to:"
  echo "    ${WORKSPACE_DIR}"
  echo "  Bash commands run inside container:"
  echo "    ${CONTAINER_NAME}"
  echo "═══════════════════════════════════════════════════════════════"
  echo ""

  cd "${AGENT_DIR}"

  # shellcheck disable=SC2086
  python -m harness.cli start \
    --task "${PROJECT_NAME}" \
    --spec "${START_MD}" \
    --project "${BENCH_DIR}" \
    --start
fi

# ── Step 5: stop runtime container (keep for next resume) ───────────
echo ""
echo "🛑 Stopping runtime container: ${CONTAINER_NAME}"
docker stop "${CONTAINER_NAME}" 2>/dev/null && echo "   ✅ Stopped" || echo "   (already stopped)"
