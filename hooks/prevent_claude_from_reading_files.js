const fs = require("node:fs");
const path = require("node:path");

const FORBIDDEN_RELATIVE_PATHS = [".env"];

function buildForbiddenIndex(cwd) {
  const canonicalPaths = new Set();
  const inodeKeys = new Set();
  for (const relative of FORBIDDEN_RELATIVE_PATHS) {
    const absolute = path.resolve(cwd, relative);
    let canonical = absolute;
    try { canonical = fs.realpathSync(absolute); } catch {}
    canonicalPaths.add(canonical);
    try {
      const stats = fs.statSync(canonical);
      inodeKeys.add(`${stats.dev}:${stats.ino}`);
    } catch {}
  }
  return { canonicalPaths, inodeKeys };
}

function canonicalize(targetPath, cwd) {
  const absolute = path.isAbsolute(targetPath) ? targetPath : path.resolve(cwd, targetPath);
  try { return fs.realpathSync(absolute); } catch {}
  let existing = absolute;
  let tail = "";
  while (!fs.existsSync(existing) && existing !== path.dirname(existing)) {
    tail = tail ? path.join(path.basename(existing), tail) : path.basename(existing);
    existing = path.dirname(existing);
  }
  try { return path.join(fs.realpathSync(existing), tail); } catch { return absolute; }
}

function isPathForbidden(canonicalPath, forbidden) {
  if (forbidden.canonicalPaths.has(canonicalPath)) return true;
  try {
    const stats = fs.statSync(canonicalPath);
    if (forbidden.inodeKeys.has(`${stats.dev}:${stats.ino}`)) return true;
  } catch {}
  return false;
}

function expandBraceAlternatives(input) {
  const openIndex = input.indexOf("{");
  if (openIndex === -1) return [input];
  let depth = 0;
  let closeIndex = openIndex;
  for (; closeIndex < input.length; closeIndex++) {
    if (input[closeIndex] === "{") depth++;
    else if (input[closeIndex] === "}") { depth--; if (depth === 0) break; }
  }
  if (closeIndex >= input.length) return [input];
  const prefix = input.slice(0, openIndex);
  const inner = input.slice(openIndex + 1, closeIndex);
  const suffix = input.slice(closeIndex + 1);
  const parts = [];
  let current = "";
  let nestedDepth = 0;
  for (const ch of inner) {
    if (ch === "{") { nestedDepth++; current += ch; }
    else if (ch === "}") { nestedDepth--; current += ch; }
    else if (ch === "," && nestedDepth === 0) { parts.push(current); current = ""; }
    else current += ch;
  }
  parts.push(current);
  if (parts.length < 2) return [input];
  const results = [];
  for (const part of parts) {
    for (const tail of expandBraceAlternatives(suffix)) {
      results.push(prefix + part + tail);
    }
  }
  return results.flatMap(expandBraceAlternatives);
}

function compileGlobSegment(segment) {
  let pattern = "^";
  let i = 0;
  while (i < segment.length) {
    const ch = segment[i];
    if (ch === "*") pattern += "[^/]*";
    else if (ch === "?") pattern += "[^/]";
    else if (ch === "[") {
      const end = segment.indexOf("]", i + 1);
      if (end === -1) { pattern += "\\["; i++; continue; }
      pattern += "[" + segment.slice(i + 1, end) + "]";
      i = end + 1;
      continue;
    } else if (/[.+^$(){}|\\]/.test(ch)) pattern += "\\" + ch;
    else pattern += ch;
    i++;
  }
  return new RegExp(pattern + "$");
}

function expandGlobToFilesystem(pattern, cwd) {
  const isAbsolute = path.isAbsolute(pattern);
  const segments = pattern.split("/").filter((s, idx) => !(isAbsolute && idx === 0 && s === ""));
  let directories = [isAbsolute ? "/" : cwd];
  for (const segment of segments) {
    const next = [];
    for (const dir of directories) {
      if (!/[*?\[]/.test(segment)) {
        next.push(path.join(dir, segment));
      } else {
        let entries;
        try { entries = fs.readdirSync(dir); } catch { continue; }
        const regex = compileGlobSegment(segment);
        for (const entry of entries) if (regex.test(entry)) next.push(path.join(dir, entry));
      }
    }
    directories = next;
  }
  return directories;
}

function expandTildeIfPresent(input) {
  if (input === "~" || input.startsWith("~/")) return path.join(process.env.HOME || "", input.slice(1));
  return input;
}

function substituteEnvVarsOrFail(input) {
  let hasUnresolvedVar = false;
  let result = input
    .replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, name) => {
      if (process.env[name] !== undefined) return process.env[name];
      hasUnresolvedVar = true; return "";
    })
    .replace(/\$([A-Za-z_][A-Za-z0-9_]*)/g, (_, name) => {
      if (process.env[name] !== undefined) return process.env[name];
      hasUnresolvedVar = true; return "";
    });
  if (/\$\(|`/.test(result)) return null;
  if (hasUnresolvedVar) return null;
  return result;
}

function expandTokenToCandidatePaths(token, cwd) {
  const substituted = substituteEnvVarsOrFail(token);
  if (substituted === null) return null;
  const tildeExpanded = expandTildeIfPresent(substituted);
  const braceExpanded = expandBraceAlternatives(tildeExpanded);
  const candidates = [];
  for (const variant of braceExpanded) {
    if (/[*?\[]/.test(variant)) {
      const matches = expandGlobToFilesystem(variant, cwd);
      if (matches.length) candidates.push(...matches);
      else candidates.push(path.resolve(cwd, variant));
    } else {
      candidates.push(path.resolve(cwd, variant));
    }
  }
  return candidates;
}

function tokenizeBashCommandIntoStatements(command) {
  const statements = [];
  let currentStatement = [];
  let currentToken = "";
  let i = 0;
  let inSingleQuote = false;
  let inDoubleQuote = false;
  const flushToken = () => {
    if (currentToken.length) { currentStatement.push(currentToken); currentToken = ""; }
  };
  const flushStatement = () => {
    flushToken();
    if (currentStatement.length) statements.push(currentStatement);
    currentStatement = [];
  };
  while (i < command.length) {
    const ch = command[i];
    if (inSingleQuote) {
      if (ch === "'") inSingleQuote = false;
      else currentToken += ch;
      i++; continue;
    }
    if (inDoubleQuote) {
      if (ch === '"') inDoubleQuote = false;
      else if (ch === "\\" && i + 1 < command.length) { currentToken += command[i + 1]; i += 2; continue; }
      else currentToken += ch;
      i++; continue;
    }
    if (ch === "'") { inSingleQuote = true; i++; continue; }
    if (ch === '"') { inDoubleQuote = true; i++; continue; }
    if (ch === "\\" && i + 1 < command.length) { currentToken += command[i + 1]; i += 2; continue; }
    if (/\s/.test(ch)) { flushToken(); i++; continue; }
    if (";|&".includes(ch)) {
      flushStatement();
      let j = i + 1;
      while (j < command.length && ";|&".includes(command[j])) j++;
      i = j;
      continue;
    }
    if ("<>".includes(ch)) {
      flushToken();
      let j = i + 1;
      while (j < command.length && "<>".includes(command[j])) j++;
      i = j;
      continue;
    }
    currentToken += ch;
    i++;
  }
  flushStatement();
  return statements;
}

function detectLinkCreationCommand(statement) {
  if (statement.length === 0) return null;
  const cmd = statement[0];
  const args = statement.slice(1);
  const hasShortFlag = (ch) => args.some(a =>
    a.startsWith("-") && !a.startsWith("--") && a.length > 1 && a.slice(1).includes(ch)
  );
  const hasLongFlag = (long) => args.some(a => a === long);
  if (cmd === "ln") return { isSymlink: hasShortFlag("s") || hasLongFlag("--symbolic") };
  if (cmd === "link") return { isSymlink: false };
  if (cmd === "cp") {
    if (hasShortFlag("s") || hasLongFlag("--symbolic-link")) return { isSymlink: true };
    if (hasShortFlag("l") || hasLongFlag("--link")) return { isSymlink: false };
  }
  return null;
}

function checkSymlinkSourceDoesNotReachForbidden(statement, cwd, forbidden) {
  const info = detectLinkCreationCommand(statement);
  if (!info || !info.isSymlink) return null;
  const args = statement.slice(1);
  const positional = args.filter(a => !a.startsWith("-"));
  if (positional.length < 1) return null;
  const sources = positional.length === 1 ? [positional[0]] : positional.slice(0, -1);
  for (const source of sources) {
    const candidates = expandTokenToCandidatePaths(source, cwd);
    if (!candidates) continue;
    for (const candidate of candidates) {
      const canonical = canonicalize(candidate, cwd);
      for (const forbiddenPath of forbidden.canonicalPaths) {
        const prefix = canonical === "/" ? "/" : canonical + "/";
        if (forbiddenPath.startsWith(prefix)) {
          return `Cannot create symlink: source "${source}" resolves to directory ${canonical} which contains forbidden path ${forbiddenPath}`;
        }
      }
    }
  }
  return null;
}

function checkBashCommandForForbiddenAccess(command, cwd, forbidden) {
  const statements = tokenizeBashCommandIntoStatements(command);
  for (const statement of statements) {
    for (const token of statement) {
      if (!token) continue;
      let toCheck = token;
      if (token.startsWith("-")) {
        const eq = token.indexOf("=");
        if (eq >= 0) toCheck = token.slice(eq + 1);
        else continue;
      }
      const candidates = expandTokenToCandidatePaths(toCheck, cwd);
      if (candidates === null) {
        return `Cannot execute command: token "${token}" contains an unresolvable expansion ($VAR or $(...) or backticks)`;
      }
      for (const candidate of candidates) {
        const canonical = canonicalize(candidate, cwd);
        if (isPathForbidden(canonical, forbidden)) {
          return `Cannot execute command: token "${token}" resolves to forbidden path ${canonical}`;
        }
      }
    }
    const linkReason = checkSymlinkSourceDoesNotReachForbidden(statement, cwd, forbidden);
    if (linkReason) return linkReason;
  }
  return null;
}

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  let toolArgs;
  try { toolArgs = JSON.parse(Buffer.concat(chunks).toString()); }
  catch (error) {
    console.error(`Hook could not parse stdin as JSON: ${error.message}`);
    process.exit(2);
  }
  const cwd = process.cwd();
  const forbidden = buildForbiddenIndex(cwd);
  const toolName = toolArgs.tool_name;

  if (toolName === "Read" || toolName === "Grep") {
    const requestedPath = toolArgs.tool_input?.file_path || toolArgs.tool_input?.path;
    if (!requestedPath) return;
    const canonical = canonicalize(requestedPath, cwd);
    if (isPathForbidden(canonical, forbidden)) {
      console.error(`Cannot ${toolName} ${requestedPath}: resolves to forbidden path ${canonical}`);
      process.exit(2);
    }
    return;
  }

  if (toolName === "Bash") {
    const command = toolArgs.tool_input?.command || "";
    const blockReason = checkBashCommandForForbiddenAccess(command, cwd, forbidden);
    if (blockReason) {
      console.error(blockReason);
      process.exit(2);
    }
  }
}

main();
