import asyncio
from cli_textual.tools.base import ToolResult

MAX_OUTPUT = 8192


async def bash_exec(command: str, working_dir: str = ".") -> ToolResult:
    """Execute a shell command and return its output.

    stdout and stderr are merged. Output is capped at 8 KB.
    """
    output_parts: list[str] = []
    exit_code = 1
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=working_dir,
        )
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(1024)
            if not chunk:
                break
            output_parts.append(chunk.decode("utf-8", errors="replace"))
        await proc.wait()
        exit_code = proc.returncode or 0
    except Exception as exc:
        return ToolResult(output=f"Error: {exc}", is_error=True, exit_code=1)

    full_output = "".join(output_parts)
    truncated = ""
    if len(full_output) > MAX_OUTPUT:
        full_output = full_output[:MAX_OUTPUT]
        truncated = "\n[output truncated]"
    return ToolResult(
        output=f"Exit code: {exit_code}\n{full_output}{truncated}",
        exit_code=exit_code,
    )
