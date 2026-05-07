#!/usr/bin/env bash
# Test battery for prevent_claude_from_writing_files.js. Focuses on .env.
# Each case pipes a synthesized PreToolUse JSON payload into the hook and
# asserts the exit code: 2 = blocked, 0 = allowed.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$HOOK_DIR/prevent_claude_from_writing_files.js"
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

echo "=== Write tool ==="
run_case "Write absolute .env path" block \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$REPO/.env\"}}"
run_case "Write relative .env path" block \
  '{"tool_name":"Write","tool_input":{"file_path":".env"}}'
run_case "Write to symlink that points to .env" block \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SOFTLINK\"}}"
run_case "Write to notes.txt (allow)" allow \
  '{"tool_name":"Write","tool_input":{"file_path":"notes.txt"}}'

echo
echo "=== Edit tool ==="
run_case "Edit .env" block \
  '{"tool_name":"Edit","tool_input":{"file_path":".env"}}'
run_case "Edit absolute .env path" block \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$REPO/.env\"}}"
run_case "Edit symlink to .env" block \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$SOFTLINK\"}}"
run_case "Edit app/handler.py (allow)" allow \
  '{"tool_name":"Edit","tool_input":{"file_path":"app/handler.py"}}'

echo
echo "=== NotebookEdit tool ==="
run_case "NotebookEdit .env" block \
  '{"tool_name":"NotebookEdit","tool_input":{"file_path":".env"}}'
run_case "NotebookEdit absolute .env path" block \
  "{\"tool_name\":\"NotebookEdit\",\"tool_input\":{\"file_path\":\"$REPO/.env\"}}"

echo
echo "=== Bash tool (write-style: redirects, cp/mv/tee, globs, links) ==="
run_case "Bash redirect: echo x > .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x > .env"}}'
run_case "Bash cp foo .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo .env"}}'
run_case "Bash mv foo .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"mv foo .env"}}'
run_case "Bash tee .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"tee .env"}}'
run_case "Bash glob bypass: cat foo > .e*" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat foo > .e*"}}'
run_case "Bash glob bypass: cat foo > .??v" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat foo > .??v"}}'
run_case "Bash redirect to symlink that points to .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x > test_softlink_to_env"}}'
run_case "Bash redirect to hardlink that points to .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x > test_hardlink_to_env"}}'
run_case "Bash ls (allow)" allow \
  '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
run_case "Bash echo hi > notes.txt (allow)" allow \
  '{"tool_name":"Bash","tool_input":{"command":"echo hi > notes.txt"}}'

echo
echo "=== Bash tool: symlink target traversal ==="
run_case "Chained mkdir + ln -s .. + redirect through link" block \
  '{"tool_name":"Bash","tool_input":{"command":"mkdir d && ln -s .. d/up && echo x > d/up/.env"}}'
run_case "ln -s .. (parent dir contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s .. evil_parent_link"}}'
run_case "ln -s . (cwd contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s . evil_self_link"}}'
run_case "ln -s / (root contains .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ln -s / evil_root_link"}}'

echo
echo "=== Adversarial: brace expansion, quoting, editor invocations, etc. ==="
run_case "Brace expansion: cp foo .e{n,m}v" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo .e{n,m}v"}}'
run_case "Brace expansion: cp foo {.,/tmp}/.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo {.,/tmp}/.env"}}'
run_case "Heredoc: cat > .env <<EOF" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat > .env <<EOF\nsecret\nEOF"}}'
run_case "Command substitution: cp foo $(echo .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo $(echo .env)"}}'
run_case "Backtick substitution: cp foo `echo .env`" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo `echo .env`"}}'
run_case "Unresolved env var: cp foo \$REPO/.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo $REPO/.env"}}'
run_case "Quoted: cp foo \".env\"" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo \".env\""}}'
run_case "Quoted: cp foo '\''.env'\''" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo '\''.env'\''"}}'
run_case "Mixed quotes: cp foo .e\"n\"v" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo .e\"n\"v"}}'
run_case "Backslash: cp foo \\.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo \\.env"}}'
run_case "vim .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"vim .env"}}'
run_case "nano .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"nano .env"}}'
run_case "sed -i on .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"sed -i s/x/y/ .env"}}'
run_case "install foo .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"install foo .env"}}'
run_case "truncate -s 0 .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"truncate -s 0 .env"}}'
run_case "Null-redirect: : > .env" block \
  '{"tool_name":"Bash","tool_input":{"command":": > .env"}}'
run_case "Append redirect: echo x >> .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x >> .env"}}'
run_case "Compound: cd /tmp && cp foo .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cd /tmp && cp foo .env"}}'
run_case "Different case: .ENV (allow on Linux)" allow \
  '{"tool_name":"Bash","tool_input":{"command":"echo x > .ENV"}}'

echo
echo "=== Adversarial: extra probes (more redirects, pipes, find, xargs, subshells) ==="
run_case "Here-string: cat <<<.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat <<<.env"}}'
run_case "exec 3> .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"exec 3> .env"}}'
run_case "exec >.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"exec >.env"}}'
run_case "Bare > .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"> .env"}}'
run_case "Bare >.env" block \
  '{"tool_name":"Bash","tool_input":{"command":">.env"}}'
run_case "cat>.env (no space)" block \
  '{"tool_name":"Bash","tool_input":{"command":"cat>.env"}}'
run_case "cp foo ./.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo ./.env"}}'
run_case "cp foo ./././.env" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo ./././.env"}}'
run_case "find . -name .env -delete" block \
  '{"tool_name":"Bash","tool_input":{"command":"find . -name .env -delete"}}'
run_case "rm -f .env && echo new > .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"rm -f .env && echo new > .env"}}'
run_case "echo x | tee -a .env" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x | tee -a .env"}}'
run_case "echo x|tee .env (no spaces around pipe)" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x|tee .env"}}'
run_case "cp foo .env;echo done (no space after ;)" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo .env;echo done"}}'
run_case "Brace group: { echo x > .env; }" block \
  '{"tool_name":"Bash","tool_input":{"command":"{ echo x > .env; }"}}'
run_case "cp -- foo .env (POSIX end-of-options)" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp -- foo .env"}}'
run_case "ENV=x cp foo .env (assignment prefix)" block \
  '{"tool_name":"Bash","tool_input":{"command":"ENV=x cp foo .env"}}'
run_case "echo x 1>.env (fd-numbered redirect)" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x 1>.env"}}'
run_case "echo x | cat > .env (right side of pipe)" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo x | cat > .env"}}'
run_case "xargs: echo .env | xargs touch" block \
  '{"tool_name":"Bash","tool_input":{"command":"echo .env | xargs touch"}}'
run_case "touch glob class: touch .e[n]v" block \
  '{"tool_name":"Bash","tool_input":{"command":"touch .e[n]v"}}'
run_case "Nested braces: cp foo .{e{n,m}v,bak}" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo .{e{n,m}v,bak}"}}'
run_case "Brace+glob: cp foo {.,/tmp}/.e*" block \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo {.,/tmp}/.e*"}}'
run_case "Literal-space variant (allow): cp foo ' .env'" allow \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo '\'' .env'\''"}}'
run_case "cp foo \$HOME/.env (resolves outside repo, allow)" allow \
  '{"tool_name":"Bash","tool_input":{"command":"cp foo $HOME/.env"}}'

echo
echo "=== Known bypasses (currently FAIL: documents holes the hook misses) ==="
# Each of these should ideally be blocked but currently slips past the
# tokenizer. They are kept here as 'block' so each run surfaces the hole.
run_case "Process substitution: tee >(cat > .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"tee >(cat > .env)"}}'
run_case "dd of=.env (key=value arg unparsed)" block \
  '{"tool_name":"Bash","tool_input":{"command":"dd if=/dev/zero of=.env"}}'
run_case "Subshell: (echo x > .env)" block \
  '{"tool_name":"Bash","tool_input":{"command":"(echo x > .env)"}}'
run_case "bash -c 'echo x > .env' (inner-shell, known limitation)" block \
  '{"tool_name":"Bash","tool_input":{"command":"bash -c '\''echo x > .env'\''"}}'
run_case "sh -c \"echo x > .env\" (inner-shell, known limitation)" block \
  '{"tool_name":"Bash","tool_input":{"command":"sh -c \"echo x > .env\""}}'
run_case "python -c 'open(\".env\",\"w\")' (interpreter arg, known limit)" block \
  '{"tool_name":"Bash","tool_input":{"command":"python -c '\''open(\".env\",\"w\")'\''"}}'
run_case "awk 'BEGIN{print > \".env\"}' (interpreter arg, known limit)" block \
  '{"tool_name":"Bash","tool_input":{"command":"awk '\''BEGIN{print > \".env\"}'\''"}}'

echo
printf 'Passed: %s, Failed: %s\n' "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]] || exit 1
