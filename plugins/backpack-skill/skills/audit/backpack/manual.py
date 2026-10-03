"""Manual: one plain-language card per skill, plus recipes (chains of skills that name each other).

Everything here is built by fixed rules from inventory.json, scan.json and audit.json.
Each card leaves "claude_note" empty: the skill's instructions let Claude fill it for a
short list, shown apart and labeled. Skill text is quoted as data, never interpreted.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .i18n import n as _n, t
from .inventory import MAX_READ, fs_path, split_frontmatter

SCHEMA_VERSION = 1
MAX_RECIPE_STEPS = 8  # a skill naming more than 7 others is an index, not a recipe

TOOLS = {"Read", "Grep", "Glob", "Write", "Edit", "NotebookEdit", "Bash", "PowerShell",
         "WebFetch", "WebSearch", "Task", "Agent", "Skill"}  # plain words for each are in i18n ("tool.<name>")
_TOOL = re.compile(r"[\w-]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WHEN_NOT = re.compile(r"\b(?:do\s+not\s+use|don'?t\s+use|not\s+for\b|never\s+use|no\s+la\s+uses|no\s+usar|no\s+es\s+para|ev[ií]tala)", re.I)
# explicit mentions only: /cmd, plugin:name, `name`, "skill name" / "name skill"; a bare word never counts
_MENTIONS = [
    re.compile(r"(?<![\w/])/([a-z0-9][\w-]*(?::[\w-]+)?)", re.I),
    re.compile(r"\b([a-z0-9][\w-]*:[a-z0-9][\w-]*)\b", re.I),
    re.compile(r"`/?([a-z0-9][\w:-]*)`", re.I),
    re.compile(r"\b(?:skill|habilidad)\s+[`'\"]?([a-z0-9][\w:-]+)", re.I),
    re.compile(r"\b([a-z0-9][\w:-]+)[`'\"]?\s+skill\b", re.I),
]


def _first_sentence(text, limit=220):
    first = _SENTENCE.split(text.strip(), maxsplit=1)[0] if text.strip() else ""
    return first if len(first) <= limit else first[:limit - 1].rstrip() + "…"


def _when_not(text):
    for sentence in _SENTENCE.split(text or ""):
        if _WHEN_NOT.search(sentence):
            return sentence.strip()
    return None


def _needs(skill, plugin_rules):
    tools = skill.get("allowed_tools") or []
    tools = tools if isinstance(tools, list) else [tools]
    words = []
    for token in (t for item in tools for t in _TOOL.findall(str(item))):
        word = t(f"tool.{token}") if token in TOOLS else (
            t("tool.mcp", server=token.split("__")[1]) if token.startswith("mcp__") and "__" in token[5:] else None)
        if word and word not in words:
            words.append(word)
    if "R12" in plugin_rules:
        words.append(t("needs.R12"))
    if "R13" in plugin_rules:
        words.append(t("needs.R13"))
    return words


def _activation(skill):
    f, cmd = skill["flags"], skill["command"]
    if not f["loaded"]:
        return t("activation.disabled")
    if f["model_invocable"] and f["user_invocable"]:
        return t("activation.both", command=cmd)
    if f["model_invocable"]:
        return t("activation.model")
    return t("activation.user", command=cmd)


def _usage(u, since):
    if u is None:
        return t("usage.none_here")
    if u["count"] == 0:
        return t("usage.unused_since", since=since) if since else t("usage.unused")
    when = t("usage.today") if u["days_unused"] == 0 else t("usage.days_ago", days=u["days_unused"])
    return t("usage.used_one", when=when) if u["count"] == 1 else t("usage.used_many", count=u["count"], when=when)


def _risk(result, rules):
    if not result or result["risk"] == "none":
        return t("risk.none")
    titles = sorted({rules[f["rule"]]["title"].lower() for f in result["findings"]})
    return t("risk.found", level=t(f"risk.level.{result['risk']}"), titles=", ".join(titles))


def _body(path):
    try:
        with open(fs_path(path), "rb") as f:
            text = f.read(MAX_READ).decode("utf-8-sig", errors="replace")
    except OSError:
        return ""
    return split_frontmatter(text)[1]


def find_mentions(text, source, by_command, by_name):
    """Skill ids named explicitly in text, in order of appearance."""
    hits = []
    for rx in _MENTIONS:
        hits += [(m.start(), m.group(1).lower()) for m in rx.finditer(text or "")]
    out = []
    for _, token in sorted(hits):
        target = by_command.get(token)
        if not target and ":" not in token:
            # a short name only reaches skills in the same space (same plugin, or both outside plugins);
            # crossing into another plugin needs its full "plugin:name" (real case: `docs` linked to anthropic-skills:docs)
            space = (source.get("plugin") or {}).get("id")
            pick = [c for c in by_name.get(token, []) if (c.get("plugin") or {}).get("id") == space]
            target = pick[0] if len(pick) == 1 else None
        if target and target["id"] != source["id"] and target["id"] not in out:
            out.append(target["id"])
    return out


def build_manual(inventory, scan, audit):
    skills = inventory["skills"]
    rules = {r["id"]: r for r in scan.get("rules", [])}
    since = audit["totals"].get("usage_history_since")
    by_command = {s["command"].lstrip("/").lower(): s for s in skills}
    by_name = {}
    for s in skills:
        by_name.setdefault(s["name"].lower(), []).append(s)

    recipes = []
    for s in skills:
        declared = s["description"] + " " + (s.get("when_to_use") or "")
        in_desc = find_mentions(declared, s, by_command, by_name)
        in_body = [t for t in find_mentions(_body(s["path"]), s, by_command, by_name) if t not in in_desc]
        if (in_desc or in_body) and len(in_desc) + len(in_body) < MAX_RECIPE_STEPS:  # longer lists are catalogs
            # ponytail: one level (the skill and what it names); follow chains deeper if recipes feel thin
            recipes.append({
                "id": f"recipe:{s['id']}",
                "title": t("recipe.title", command=s["command"]),
                "steps": [s["id"]] + in_desc + in_body,
                "declared_in": {**{t: "description" for t in in_desc}, **{t: "body" for t in in_body}},
            })
    recipes_of = {}
    for r in recipes:
        for sid in r["steps"]:
            recipes_of.setdefault(sid, []).append(r["id"])

    cards = {}
    for s in skills:
        sid = s["id"]
        a = audit["skills"][sid]
        plugin_result = scan.get("plugins", {}).get(s["plugin"]["id"]) if s.get("plugin") else None
        plugin_rules = {f["rule"] for f in (plugin_result or {}).get("findings", [])}
        tok = s["tokens"]
        cards[sid] = {
            "name": s["name"],
            "command": s["command"],
            "what": _first_sentence(s["description"]) or t("card.no_description"),
            "activation": _activation(s),
            "triggers": s.get("when_to_use"),
            "how_to_call": f"{s['command']} {s['argument_hint']}" if s.get("argument_hint") else s["command"],
            "needs": _needs(s, plugin_rules),
            "when_not": _when_not(s["description"] + " " + (s.get("when_to_use") or "")),
            "usage": _usage(a.get("usage"), since),
            "weight": t("card.weight", fixed=_n(tok["fixed"]), body=_n(tok["body"])),
            "risk": _risk(scan.get("skills", {}).get(sid), rules),
            "light": a["light"],
            "recommendation": a["recommendation"],
            "reasons": [r["text"] for r in a["reasons"]],
            "recipes": recipes_of.get(sid, []),
            "claude_note": None,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cards": cards,
        "recipes": recipes,
    }


def shortlist(inventory, audit, manual, limit=40):
    """Skills worth a plain-language note from Claude: the ones that stay or need a look
    (not the ones to remove). Skill text goes out marked as data for Claude to explain."""
    keep = [s for s in inventory["skills"] if audit["skills"][s["id"]]["recommendation"] != "remove"]
    used = lambda s: (audit["skills"][s["id"]].get("usage") or {}).get("count", 0)
    keep.sort(key=lambda s: (-used(s), -s["tokens"]["fixed"], s["id"]))
    return [{
        "id": s["id"],
        "command": s["command"],
        "recommendation": audit["skills"][s["id"]]["recommendation"],
        "reasons": [r["text"] for r in audit["skills"][s["id"]]["reasons"]],
        "needs": manual["cards"][s["id"]]["needs"],
        "usage": manual["cards"][s["id"]]["usage"],
        "skill_text_untrusted": s["description"][:600],
    } for s in keep[:limit]]


def write_manual(manual, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manual.json"
    path.write_text(json.dumps(manual, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
