# Plan: Robust write-file validator hook

## Context

`hooks/prevent_claude_from_reading_files.js` is a thorough validator: it canonicalizes paths, follows symlinks, expands tildes, env vars, brace alternatives and globs, and tokenizes Bash to inspect every argument — blocking access to `.env` even via tricks like `cat .??v`, hard links, `ln -s .. evil/` traversal, etc.

`hooks/prevent_claude_from_writing_files.js` is naive: a plain `String.includes` check on the path/command. It's bypassable (e.g. brace expansion, symlinks, env-var-built paths) and duplicates none of the careful logic from the read hook.

Goal: make the write hook as strict as the read hook for the `.env` file, **without duplicating code**. Extract the shared validation utilities into a third module that both hooks import. The user will wire the hook into `.claude/settings.json` themselves (the `Write|Edit|NotebookEdit|Bash` matcher is already in place).

## Approach

Three files in `hooks/`:

1. **`hooks/forbidden_paths_lib.js`** *(new)* — exports every utility currently in the read hook, parameterized so each caller supplies its own forbidden list:
   - `buildForbiddenIndex(cwd, relativePaths)`
   - `canonicalize(targetPath, cwd)`
   - `isPathForbidden(canonicalPath, forbidden)`
   - `expandBraceAlternatives`, `compileGlobSegment`, `expandGlobToFilesystem`, `expandTildeIfPresent`, `substituteEnvVarsOrFail`, `expandTokenToCandidatePaths`
   - `tokenizeBashCommandIntoStatements`
   - `detectLinkCreationCommand`, `checkSymlinkSourceDoesNotReachForbidden`
   - `checkBashCommandForForbiddenAccess(command, cwd, forbidden)`
   - `readToolArgsFromStdin()` — small helper that reads stdin and JSON-parses it (currently inlined in `main()` of the read hook); shared because both hooks need it.

   No behavior change: the bodies are moved verbatim from `prevent_claude_from_reading_files.js`. The only edit is converting the module-level `FORBIDDEN_RELATIVE_PATHS` constant into a parameter of `buildForbiddenIndex`.

2. **`hooks/prevent_claude_from_reading_files.js`** *(refactored)* — becomes a thin dispatcher:
   - Declares `const FORBIDDEN_RELATIVE_PATHS = [".env"];`
   - `require`s the lib
   - `main()` reads stdin, builds the forbidden index, and dispatches:
     - `Read` / `Grep` → canonicalize `tool_input.file_path || tool_input.path`, exit 2 if forbidden.
     - `Bash` → `checkBashCommandForForbiddenAccess`, exit 2 if a reason is returned.

3. **`hooks/prevent_claude_from_writing_files.js`** *(rewritten)* — same shape as the refactored read hook, different dispatch:
   - `const FORBIDDEN_RELATIVE_PATHS = [".env"];`
   - `Write` / `Edit` / `NotebookEdit` → canonicalize `tool_input.file_path || tool_input.path`, exit 2 if forbidden.
   - `Bash` → reuse `checkBashCommandForForbiddenAccess`. This blocks every bash command that even *names* `.env` (matching what the read hook does today). That is intentional defense-in-depth — a redirect like `echo x > .env`, a `cp foo .env`, `mv foo .env`, `tee .env`, `sed -i .env`, etc. all surface `.env` as a token, so the existing token scanner already catches them. Trying to specifically distinguish "writes" from "reads" in Bash would require modeling each command's argument semantics and is not worth the complexity for a single forbidden file.
   - Drops the stray `console.log(writePath)` from the current hook (it pollutes hook output).

The list of forbidden paths stays per-hook so the two hooks can diverge later (e.g. forbidding writes to `.claude/settings.json` while still allowing reads). For now both lists are `[".env"]`.

## Critical files

- `hooks/forbidden_paths_lib.js` *(new)*
- `hooks/prevent_claude_from_reading_files.js` *(refactor — no behavior change)*
- `hooks/prevent_claude_from_writing_files.js` *(rewrite)*
- `.claude/settings.json` — **not modified**; the user will handle wiring (the write matcher is already present).
- `hooks/tests/run.sh` — existing test battery for the read hook; left alone in this change. (Optional follow-up: add a parallel `run_write.sh` mirroring the same cases against `Write` / `Edit` / `NotebookEdit` and Bash write commands. Not in scope unless the user asks.)

## Verification

After implementing, run from the repo root:

```bash
bash hooks/tests/run.sh
```

This covers the read hook end-to-end. All cases must still pass — the refactor must be behavior-preserving for it.

Then sanity-check the write hook manually with a few synthesized payloads:

```bash
# expect exit 2 (blocked)
printf '{"tool_name":"Write","tool_input":{"file_path":".env"}}' | node hooks/prevent_claude_from_writing_files.js; echo $?
printf '{"tool_name":"Edit","tool_input":{"file_path":".env"}}'  | node hooks/prevent_claude_from_writing_files.js; echo $?
printf '{"tool_name":"Bash","tool_input":{"command":"echo x > .env"}}' | node hooks/prevent_claude_from_writing_files.js; echo $?
printf '{"tool_name":"Bash","tool_input":{"command":"cp foo .e*"}}'    | node hooks/prevent_claude_from_writing_files.js; echo $?

# expect exit 0 (allowed)
printf '{"tool_name":"Write","tool_input":{"file_path":"notes.txt"}}'  | node hooks/prevent_claude_from_writing_files.js; echo $?
printf '{"tool_name":"Bash","tool_input":{"command":"ls"}}'            | node hooks/prevent_claude_from_writing_files.js; echo $?
```

Once the user wires the hook (already wired in `.claude/settings.json`), normal Claude Code use will exercise it.
