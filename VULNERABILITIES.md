# Vulnerabilities in the forbidden-paths hooks

This document catalogs the bypasses found in the current implementation of
`hooks/prevent_claude_from_writing_files.js` and `hooks/prevent_claude_from_reading_files.js`,
both of which delegate Bash inspection to `checkBashCommandForForbiddenAccess`
in `hooks/forbidden_paths_lib.js`. Every bypass below applies to **both hooks**,
since they share that function.

The protected file is `.env` (relative to the repo cwd).

Each entry was discovered by `hooks/tests/run_write.sh` and is kept in the
"Known bypasses" section of that script as a `block`-expected case, so future
runs continue to surface the hole until it is fixed.

---

## 1. Process substitution — `tee >(cat > .env)`

**Payload**
```bash
tee >(cat > .env)
```

**Result:** hook exits 0 (allowed). Should be blocked.

**Root cause:** `tokenizeBashCommandIntoStatements` does not treat `(` or `)`
as token delimiters. The command tokenizes to `["tee", "(cat", ".env)"]`.
Neither `(cat` nor `.env)` resolves to `.env` after `path.resolve`, so the
forbidden-path check misses it.

**Fix sketch:** strip leading `(` and trailing `)` from tokens, or split on
those characters the way the tokenizer already splits on `;|&` and `<>`.

---

## 2. Subshell parens — `(echo x > .env)`

**Payload**
```bash
(echo x > .env)
```

**Result:** hook exits 0 (allowed). Should be blocked.

**Root cause:** identical to #1 — `(` sticks to `echo` and `)` sticks to
`.env`, producing tokens that don't match the forbidden path.

**Fix sketch:** same as #1.

---

## 3. `key=value` argument syntax — `dd of=.env`

**Payload**
```bash
dd if=/dev/zero of=.env
```

**Result:** hook exits 0 (allowed). Should be blocked.

**Root cause:** in `checkBashCommandForForbiddenAccess`, the `name=value`
prefix is only stripped when **the token starts with `-`**:

```js
if (token.startsWith("-")) {
  const eq = token.indexOf("=");
  if (eq >= 0) toCheck = token.slice(eq + 1);
  else continue;
}
```

So `of=.env` is checked as a literal path and canonicalizes to
`<repo>/of=.env`, which is not forbidden. The same hole applies to any
command using `key=value` arguments (`dd if=/of=`, `tar f=`, custom CLIs).

**Fix sketch:** also strip the `name=` prefix on tokens that don't start
with `-` (or, more conservatively, on tokens whose left side matches
`/^[A-Za-z_][A-Za-z0-9_]*$/`), then check the right side.

---

## 4. Wrapper commands that re-interpret a quoted argument

These rely on the outer Bash tokenizer never recursing into a script string
that another interpreter will re-parse. The plan acknowledges this class as
out of scope, but it is the largest practical bypass surface, so it is listed
here for completeness.

**Payloads (all currently allowed by the hook):**
```bash
bash -c 'echo x > .env'
sh -c "echo x > .env"
python -c 'open(".env","w")'
awk 'BEGIN{print > ".env"}'
```

**Result:** hook exits 0 (allowed). Should arguably be blocked.

**Root cause:** the inner script is delivered as a single quoted token
(`echo x > .env`, `open(".env","w")`, etc.). The Bash tokenizer treats it as
one opaque string that contains spaces — it never tokenizes its insides — so
`.env` never appears as a standalone token to be canonicalized.

This generalizes to anything of the form `<interpreter> -c <quoted-script>`,
including `perl -e`, `ruby -e`, `node -e`, `zsh -c`, `dash -c`, etc.

**Fix sketch (none clean):** modeling per-command argument semantics is
exactly what the plan declined to do. A partial mitigation is to grep
the **raw command string** (not just tokens) for any forbidden basename
and block on a substring match — at the cost of false positives whenever a
command legitimately mentions `.env` (e.g., `grep ENV docs/setup.md`).

---

## Successful defenses (for reference)

The following adversarial inputs **are** correctly blocked by the current
implementation, and are kept in `run_write.sh` as regression coverage:

- Brace expansion: `cp foo .e{n,m}v`, `cp foo {.,/tmp}/.env`, `cp foo .{e{n,m}v,bak}`, `cp foo {.,/tmp}/.e*`
- Globs: `cat foo > .e*`, `cat foo > .??v`, `touch .e[n]v`
- Quoting variants: `cp foo ".env"`, `cp foo '.env'`, `cp foo .e"n"v`, `cp foo \.env`
- Heredoc: `cat > .env <<EOF ... EOF`
- Command/backtick substitution: `cp foo $(echo .env)`, `` cp foo `echo .env` `` (rejected as unresolvable)
- Unresolved env vars: `cp foo $REPO/.env` (rejected as unresolvable)
- No-space redirects: `cat>.env`, `>.env`, `> .env`
- Fd-numbered redirects: `echo x 1>.env`, `exec 3> .env`
- Append redirect: `echo x >> .env`
- POSIX end-of-options: `cp -- foo .env`
- Assignment prefix: `ENV=x cp foo .env`
- Brace group: `{ echo x > .env; }`
- Compound: `cd /tmp && cp foo .env`
- Pipes: `echo x | cat > .env`, `echo x | tee -a .env`, `echo x|tee .env`
- xargs: `echo .env | xargs touch`
- Editor invocations: `vim .env`, `nano .env`, `sed -i s/x/y/ .env`
- Other write tools: `install foo .env`, `truncate -s 0 .env`, `: > .env`, `echo new > .env` after `rm -f .env`
- Symlink/hardlink traversal: `ln -s ..`, `ln -s .`, `ln -s /`, `mkdir d && ln -s .. d/up && echo x > d/up/.env`, redirects to a softlink/hardlink that points to `.env`

---

## Test harness

- `hooks/tests/run.sh` — covers the read hook (Read / Grep / Bash). All cases pass.
- `hooks/tests/run_write.sh` — covers the write hook (Write / Edit / NotebookEdit / Bash). The 7 currently-failing cases are exactly the bypasses documented above (#1–#4, where #4 is split into 4 wrapper-command variants).

Run from the repo root:
```bash
bash hooks/tests/run.sh
bash hooks/tests/run_write.sh
```
