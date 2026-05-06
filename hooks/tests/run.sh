#!/usr/bin/env bash
# Test battery for prevent_claude_from_reading_files.js. Focuses on .env.
# Each case pipes a synthesized PreToolUse JSON payload into the hook and
# asserts the exit code: 2 = blocked, 0 = allowed.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$HOOK_DIR/prevent_claude_from_reading_files.js"
REPO="$(cd "$HOOK_DIR/.." && pwd)"
cd "$REPO" || { echo "cannot cd to $REPO" >&2; exit 1; }

SOFTLINK="$REPO/test_softlink_to_env"
HARDLINK="$REPO/test_hardlink_to_env"
PASS=0
FAIL=0

cleanup() { rm -f "$SOFTLINK" "$HARDLINK"; }
trap cleanup EXIT

run_case() {
  local name="$1" expect="$2" payload="$3"
  local out rc
  out=$(printf '%s' "$payload" | node "$HOOK" 2>&1)
  rc=$?
  if [[ "$expect" == "block" && $rc -eq 2 ]] || [[ "$expect" == "allow" && $rc -eq 0 ]]; then
    printf 'OK    %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf 'FAIL  %s (expected %s, got exit %s)\n  output: %s\n' "$name" "$expect" "$rc" "$out"
    FAIL=$((FAIL + 1))
  fi
}

# Setup: a symlink and a hardlink that both point at .env.
ln -sf .env "$SOFTLINK"
ln -f .env "$HARDLINK"

echo "=== Read tool ==="
run_case "Read absolute .env path" block \
  "{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$REPO/.env\"}}"
run_case "Read relative .env path" block \
  '{"tool_name":"Read","tool_input":{"file_path":".env"}}'
run_case "Read symlink that points to .env" block \
  "{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$SOFTLINK\"}}"

echo
echo "=== Grep tool ==="
run_case "Grep with path=.env" block \
  '{"tool_name":"Grep","tool_input":{"path":".env","pattern":"PASSWORD"}}'
run_case "Grep with path=symlink to .env" block \
  "{\"tool_name\":\"Grep\",\"tool_input\":{\"path\":\"$SOFTLINK\",\"pattern\":\"PASSWORD\"}}"

echo
echo "=== Bash tool (5 cases: plain, 2 globs, soft link, hard link) ==="
run_case "Bash plain read: cat .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}'
run_case "Bash glob bypass: cat .??v" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat .??v"}}'
run_case "Bash glob bypass: cat .e*" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat .e*"}}'
run_case "Bash soft link: cat <symlink-to-.env>" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat test_softlink_to_env"}}'
run_case "Bash hard link: cat <hardlink-to-.env>" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat test_hardlink_to_env"}}'

echo
echo "=== Bash tool: symlink target traversal ==="
run_case "Chained mkdir + ln -s .. + cat through link" block \
  '{"tool_name":"Bash","tool_input":{"command":"mkdir d && ln -s .. d/up && cat d/up/.env"}}'
run_case "ln -s .. (parent dir contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s .. evil_parent_link"}}'
run_case "ln -s . (cwd contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s . evil_self_link"}}'
run_case "ln -s / (root contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s / evil_root_link"}}'

echo
printf 'Passed: %s, Failed: %s\n' "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
