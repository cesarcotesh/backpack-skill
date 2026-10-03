"""Skill usage from Claude session logs.

Privacy rule: only skill names and dates leave this module. Lines that can't hold
an invocation are skipped unparsed; from the rest, only the Skill tool's "skill"
field, a plugin agent's name ("subagent_type"), the <command-name> tag and the
timestamp are read. Arguments, messages and
tool results are never kept.

Logs (Claude Code docs, claude-directory): ~/.claude/projects/<project>/<session>.jsonl,
with subagent logs under <session>/subagents/. The desktop app keeps its own
.claude/projects inside local-agent-mode-sessions (layout read from a real install).
Claude Code deletes old logs (cleanupPeriodDays, 30 days by default), so usage only
covers the history still on disk; history_since says from when.
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .inventory import fs_path, plain

SCHEMA_VERSION = 1
_COMMAND = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")


def log_dirs(home, app_data=None):
    dirs = [fs_path(home) / ".claude" / "projects"]
    if app_data:
        sessions = fs_path(app_data) / "local-agent-mode-sessions"
        dirs += sorted(sessions.glob("*/*/local_*/.claude/projects"))
        dirs += sorted(sessions.glob("*/*/agent/*/.claude/projects"))
    return [d for d in dirs if d.is_dir()]


def invocations(line):
    """(skill name, ISO timestamp) pairs found in one log line. Nothing else is returned."""
    if '"Skill"' not in line and "<command-name>" not in line and '"subagent_type"' not in line:
        return []
    try:
        entry = json.loads(line)
    except ValueError:
        return []
    message = entry.get("message") if isinstance(entry, dict) else None
    if not isinstance(message, dict):
        return []
    stamp = entry.get("timestamp")
    content = message.get("content")
    found = []
    if isinstance(content, str) and message.get("role") == "user":
        found += _COMMAND.findall(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                skill = (block.get("input") or {}).get("skill")
                if isinstance(skill, str) and skill.strip():
                    found.append(skill.strip().lstrip("/"))
            elif block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                agent = (block.get("input") or {}).get("subagent_type")  # a plugin agent counts as using its plugin
                if isinstance(agent, str) and ":" in agent:
                    found.append(agent.strip())
            elif block.get("type") == "text" and message.get("role") == "user":
                found += _COMMAND.findall(block.get("text") or "")
    return [(name, stamp) for name in found if isinstance(stamp, str)]


def _first_timestamp(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    return None


def build_usage(home, app_data=None):
    skills, files, oldest = {}, 0, None
    for d in log_dirs(home, app_data):
        for path in sorted(d.rglob("*.jsonl")):
            files += 1
            first = _first_timestamp(path)
            if first and (oldest is None or first < oldest):
                oldest = first
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    for name, stamp in invocations(line):
                        day = stamp[:10]
                        rec = skills.setdefault(name, {"count": 0, "first_used": day, "last_used": day})
                        rec["count"] += 1
                        rec["first_used"] = min(rec["first_used"], day)
                        rec["last_used"] = max(rec["last_used"], day)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"log_dirs": [plain(d) for d in log_dirs(home, app_data)], "files": files},
        "history_since": oldest[:10] if oldest else None,
        "skills": dict(sorted(skills.items())),
    }


def days_since(day, today=None):
    today = today or date.today()
    return (today - date.fromisoformat(day)).days


def write_usage(usage, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "usage.json"
    path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
