const FORBIDDEN_FILES = [".env", ".claude/settings.json", "hooks/prevent_claude_from_reading_files.js"]

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const toolArgs = JSON.parse(Buffer.concat(chunks).toString());

  const readPath = toolArgs.tool_input?.file_path || toolArgs.tool_input?.path || "";
  console.log(readPath)

  if (string_contains_some_of(readPath, FORBIDDEN_FILES)) {
    console.error(`Cannot read ${readPath} because there's a path forbidden by the user`);
    process.exit(2);
  }

  if (toolArgs.tool_name === "Bash") {
    const command = toolArgs.tool_input?.command || "";
    if (string_contains_some_of(command, FORBIDDEN_FILES)) {
      console.error(`Cannot execute ${command} because there's a path forbidden by the user`);
      process.exit(2);
    }
  }
}

function string_contains_some_of(command, file_names){
  for(const file_name of file_names){
    if (command.includes(file_name)) return true;
  }
  return false;
}

main();
