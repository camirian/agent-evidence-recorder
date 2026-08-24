"""Agent Evidence ingest-session: turn a real Claude Code session transcript into a
structured run record.

This extracts the "what actually happened" ground truth -- the tool calls, the
bash commands, and the files written/edited -- which is exactly what the agent
*cannot narrate around* in its summary. It does NOT trust the agent's prose; it
reads the actions.

Reads a Claude Code `.jsonl` session file (one JSON object per line). stdlib
only. `--redact` omits free text (intent/commands) for privacy-safe sharing.
"""

from __future__ import annotations

import json
from pathlib import Path

_FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _text_from_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"]
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        )
    return ""


def ingest_session(path, redact: bool = False) -> dict:
    path = Path(path)
    session_id = cwd = git_branch = version = None
    started_at = ended_at = None
    intent = ""
    user_turns = assistant_turns = 0
    tools: dict[str, int] = {}
    commands: list[str] = []
    files_touched: set[str] = set()
    models: set[str] = set()
    last_stop_reason = None
    pr_links: list[dict] = []

    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = session_id or obj.get("sessionId")
            cwd = cwd or obj.get("cwd")
            git_branch = git_branch or obj.get("gitBranch")
            version = version or obj.get("version")
            ts = obj.get("timestamp")
            if ts:
                started_at = ts if started_at is None or ts < started_at else started_at
                ended_at = ts if ended_at is None or ts > ended_at else ended_at

            if obj.get("type") == "pr-link":
                pr_links.append(
                    {"number": obj.get("prNumber"), "url": obj.get("prUrl"), "repo": obj.get("prRepository")}
                )

            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")

            if role == "user":
                text = _text_from_content(content)
                if text.strip():
                    user_turns += 1
                    if not intent:
                        intent = text.strip()
            elif role == "assistant":
                assistant_turns += 1
                if message.get("model"):
                    models.add(message["model"])
                if message.get("stop_reason"):
                    last_stop_reason = message["stop_reason"]
                if isinstance(content, list):
                    for block in content:
                        if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                            continue
                        name = block.get("name", "?")
                        tools[name] = tools.get(name, 0) + 1
                        inp = block.get("input") or {}
                        if name == "Bash" and isinstance(inp.get("command"), str):
                            commands.append(inp["command"])
                        if name in _FILE_TOOLS and isinstance(inp.get("file_path"), str):
                            files_touched.add(inp["file_path"])

    record = {
        "session_id": session_id,
        "cwd": cwd,
        "git_branch": git_branch,
        "version": version,
        "started_at": started_at,
        "ended_at": ended_at,
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "tools": dict(sorted(tools.items())),
        "command_count": len(commands),
        "models": sorted(models),
        "last_stop_reason": last_stop_reason,
        "pr_links": pr_links,
    }
    if redact:
        record["intent"] = "[redacted]" if intent else ""
        record["commands"] = "[redacted]"
        record["files_touched"] = [f"[{len(files_touched)} files]"]
    else:
        record["intent"] = (intent[:280] + "…") if len(intent) > 280 else intent
        record["commands"] = commands
        record["files_touched"] = sorted(files_touched)
    return record
