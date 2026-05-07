const {
  buildForbiddenIndex,
  canonicalize,
  isPathForbidden,
  checkBashCommandForForbiddenAccess,
  readToolArgsFromStdin,
} = require("./forbidden_paths_lib.js");

const FORBIDDEN_RELATIVE_PATHS = [".env"];

async function main() {
  const toolArgs = await readToolArgsFromStdin();
  const cwd = process.cwd();
  const forbidden = buildForbiddenIndex(cwd, FORBIDDEN_RELATIVE_PATHS);
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