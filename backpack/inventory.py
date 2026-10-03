"""Skill inventory: finds installed Claude Code skills and estimates their token weight.

Read-only by design. Skill files are read as text and treated as data: nothing in
them is executed or obeyed. The only write is inventory.json in the output dir.

Locations follow the Claude Code docs (code.claude.com/docs/en/skills and
/plugins/loading): personal ~/.claude/skills, project .claude/skills, plugins
from ~/.claude/plugins/installed_plugins.json (cache/<marketplace>/<plugin>/<version>),
and plugin folders saved under a skills dir (the "@skills-dir" origin).

The Claude desktop app keeps its own plugins and the skills synced from claude.ai
in its data folder (--app-data). That layout is not documented; it was read from
a real install (local-agent-mode-sessions/<org>/<user>/rpm and .../skills-plugin).
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
CHARS_PER_TOKEN = 3.7  # ponytail: char heuristic from SPEC; exact counts need the Anthropic API (network)
LISTING_CAP = 1536  # description + when_to_use are cut here in the skill listing (Claude Code docs)
MAX_READ = 1_000_000  # bytes read per file

_KEY = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")


def estimate_tokens(text):
    return round(len(text) / CHARS_PER_TOKEN)


def fs_path(path):
    """Absolute path that still works past Windows' 260-character limit.
    Without the \\\\?\\ prefix, Python silently fails to see files in deep plugin folders."""
    p = os.path.abspath(str(path))
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
    return Path(p)


def plain(path):
    """Path as text for reports, without the Windows long-path prefix."""
    s = str(path)
    if s.startswith("\\\\?\\UNC\\"):
        return "\\\\" + s[8:]
    return s[4:] if s.startswith("\\\\?\\") else s


def _warn(warnings, path, code, message):
    warnings.append({"path": plain(path), "code": code, "message": message})


def _read_bytes(path, warnings):
    with open(path, "rb") as f:
        raw = f.read(MAX_READ + 1)
    if len(raw) > MAX_READ:
        _warn(warnings, path, "file_truncated", "Archivo muy grande; solo se leyó el primer megabyte.")
        raw = raw[:MAX_READ]
    return raw


def _read_json(path, warnings):
    """Parsed JSON, or None when the file is missing or unreadable (the latter is warned)."""
    if not path.is_file():
        return None
    try:
        return json.loads(_read_bytes(path, warnings).decode("utf-8-sig"))
    except (OSError, ValueError):
        _warn(warnings, path, "json_unreadable", "No se pudo leer este archivo JSON.")
        return None


# --- frontmatter ---------------------------------------------------------------

def split_frontmatter(text):
    """Return (frontmatter_lines or None, body, closed)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, True
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:]), True
    return None, text, False


def _unquote(s):
    if len(s) >= 2 and s[0] == s[-1] == '"':
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        return [_unquote(p.strip()) for p in s[1:-1].split(",") if p.strip()]
    return s


def _scalar(value, block):
    children = [b.strip() for b in block if b.strip()]
    if value[:1] in ("|", ">"):
        # ponytail: ignores chomping/indent indicators and inner blank lines; enough for descriptions
        return ("\n" if value[0] == "|" else " ").join(children)
    if not value and children and all(c == "-" or c.startswith("- ") for c in children):
        return [_unquote(c[1:].strip()) for c in children]
    if not value and children:
        return "\n".join(children)  # nested mapping, kept as raw text
    return _unquote(" ".join([value] + children))


def parse_frontmatter(lines):
    """Minimal YAML subset for SKILL.md headers. Returns (data, unparsed_lines)."""
    data, bad = {}, []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if not m:
            bad.append(line)
            continue
        block = []
        # indented lines, or "- item" lines at column 0 (a valid YAML list under a key)
        while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t-"):
            block.append(lines[i])
            i += 1
        data[m.group(1)] = _scalar(m.group(2).strip(), block)
    return data, bad


def _is_true(value):
    return str(value).strip().lower() == "true"


def _as_text(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


# --- origin ----------------------------------------------------------------------

def _inside(path, folder):
    a, b = os.path.normcase(plain(path)), os.path.normcase(plain(folder))
    return a.startswith(b.rstrip("\\/") + os.sep)


def detect_origin(skill_dir, plugin, npx_root, warnings):
    if plugin:
        if plugin.get("via") == "claude.ai":
            return {"type": "claude.ai"}
        origin = {"type": "plugin", "marketplace": plugin["marketplace"]}
        return {**origin, "via": plugin["via"]} if plugin.get("via") else origin
    if skill_dir.is_symlink() or getattr(skill_dir, "is_junction", lambda: False)():
        target = skill_dir.resolve()
        # `npx skills` keeps the real copy in ~/.agents/skills and links it into ~/.claude/skills
        kind = "npx-skills" if npx_root and _inside(target, npx_root) else "symlink"
        return {"type": kind, "target": plain(target)}
    git = skill_dir / ".git"
    if git.exists():
        remote = None
        config = git / "config"
        if config.is_file():
            text = _read_bytes(config, warnings).decode("utf-8", errors="replace")
            m = re.search(r"^\s*url\s*=\s*(\S+)", text, re.M)
            # never copy credentials embedded in a remote URL into the report
            remote = re.sub(r"//[^/@\s]+@", "//", m.group(1)) if m else None
        return {"type": "git", "remote": remote}
    return {"type": "unknown"}


# --- skills ----------------------------------------------------------------------

def read_skill(skill_md, dir_name, scope, plugin, warnings, skill_enabled=None, npx_root=None):
    raw = _read_bytes(skill_md, warnings)
    text = raw.decode("utf-8-sig", errors="replace")
    fm_lines, body, closed = split_frontmatter(text)
    if not closed:
        _warn(warnings, skill_md, "frontmatter_unclosed", "El encabezado (frontmatter) no se cierra con '---'.")
    fm, bad = parse_frontmatter(fm_lines or [])
    if bad:
        _warn(warnings, skill_md, "frontmatter_unparsed", f"{len(bad)} línea(s) del encabezado no se entendieron.")
    malformed = not closed or bool(bad)
    if malformed:  # Claude Code loads a skill with malformed frontmatter with empty metadata
        fm = {}

    name = _as_text(fm.get("name")).strip() or dir_name
    description = _as_text(fm.get("description")).strip()
    if not description and not malformed:  # Claude Code falls back to the first non-empty markdown line
        description = next((l.strip() for l in body.splitlines() if l.strip() and l.strip() != "---"), "")
    when_to_use = _as_text(fm.get("when_to_use")).strip()
    listing = (description + (" " + when_to_use if when_to_use else ""))[:LISTING_CAP]

    model_invocable = not _is_true(fm.get("disable-model-invocation"))
    loaded = (plugin is None or plugin["enabled"] is not False) and skill_enabled is not False
    return {
        "name": name,
        "command": f"/{plugin['name']}:{name}" if plugin else f"/{name}",
        "scope": scope,
        "path": plain(skill_md),
        "description": description,
        "plugin": plugin,
        "flags": {
            "model_invocable": model_invocable,
            "user_invocable": str(fm.get("user-invocable", "true")).strip().lower() != "false",
            "loaded": loaded,
        },
        "allowed_tools": fm.get("allowed-tools"),
        "tokens": {
            "fixed": estimate_tokens(f"{name}: {listing}") if model_invocable and loaded else 0,
            "body": estimate_tokens(body),
            "estimated": True,
        },
        "sha256": hashlib.sha256(raw).hexdigest(),
        "origin": detect_origin(skill_md.parent, plugin, npx_root, warnings),
    }


def _skill_dirs(skills_dir):
    if not skills_dir.is_dir():
        return []
    return sorted(d for d in skills_dir.iterdir() if (d / "SKILL.md").is_file())


def _plugin_dirs(skills_dir):
    if not skills_dir.is_dir():
        return []
    return sorted(d for d in skills_dir.iterdir() if (d / ".claude-plugin" / "plugin.json").is_file())


def enabled_plugins(home, projects, warnings):
    """Merged enabledPlugins map from user, project and local settings."""
    files = [home / ".claude" / "settings.json"]
    files += [p / ".claude" / n for p in projects for n in ("settings.json", "settings.local.json")]
    merged = {}
    for f in files:
        data = _read_json(f, warnings)
        if isinstance(data, dict) and isinstance(data.get("enabledPlugins"), dict):
            merged.update(data["enabledPlugins"])  # ponytail: one map across projects, per-project view if needed
    return merged


def installed_plugin_roots(plugins_dir, warnings):
    """[(plugin_id, install_path)] from installed_plugins.json, else from the cache layout."""
    data = _read_json(plugins_dir / "installed_plugins.json", warnings)
    if isinstance(data, dict) and isinstance(data.get("plugins"), dict):
        roots = {}
        for pid, entries in data["plugins"].items():
            for entry in entries if isinstance(entries, list) else [entries]:
                if isinstance(entry, dict) and entry.get("installPath"):
                    roots.setdefault(fs_path(entry["installPath"]), pid)
        return sorted((pid, path) for path, pid in roots.items())
    # ponytail: no install record, so take the last version dir by name per plugin
    out = []
    cache = plugins_dir / "cache"
    for mkt in sorted(cache.iterdir()) if cache.is_dir() else []:
        for plug in sorted(mkt.iterdir()) if mkt.is_dir() else []:
            versions = sorted(v for v in plug.iterdir() if v.is_dir()) if plug.is_dir() else []
            if versions:
                out.append((f"{plug.name}@{mkt.name}", versions[-1]))
    return out


def plugin_skills(root, plugin_id, marketplace, enabled_map, warnings, via=None):
    """Skills of one plugin root as (skill_dir, dir_name, plugin) tuples."""
    manifest = _read_json(root / ".claude-plugin" / "plugin.json", warnings) or {}
    name = manifest.get("name") or (plugin_id or root.name).split("@")[0]
    plugin_id = plugin_id or f"{name}@{marketplace}"
    enabled = enabled_map.get(plugin_id)
    if not isinstance(enabled, bool):
        enabled = manifest.get("defaultEnabled", True) if marketplace == "skills-dir" else None
    plugin = {"id": plugin_id, "name": name, "marketplace": marketplace, "enabled": enabled, "root": plain(root)}
    if via:
        plugin["via"] = via
    if (root / "skills").is_dir():
        return [(d, d.name, plugin) for d in _skill_dirs(root / "skills")]
    if (root / "SKILL.md").is_file():  # single-skill plugin
        return [(root, name, plugin)]
    return []


def app_skills(app_data, enabled_map, warnings):
    """Skills the Claude desktop app loads by itself, as (skill_dir, dir_name, plugin, skill_enabled).
    - its plugins: local-agent-mode-sessions/<org>/<user>/rpm/<plugin id>/, described in rpm/manifest.json
    - skills synced from claude.ai: local-agent-mode-sessions/skills-plugin/<org>/<user>/, with a
      per-skill "enabled" flag in its manifest.json
    """
    found = []
    sessions = app_data / "local-agent-mode-sessions"
    for rpm in sorted(sessions.glob("*/*/rpm")):
        listed = (_read_json(rpm / "manifest.json", warnings) or {}).get("plugins") or []
        meta = {p.get("id"): p for p in listed if isinstance(p, dict)}
        for root in sorted(d for d in rpm.iterdir() if d.is_dir()):
            mkt = meta.get(root.name, {}).get("marketplaceName") or "app"
            found += [(d, n, plug, None) for d, n, plug in plugin_skills(root, None, mkt, enabled_map, warnings, via="app")]
    for root in sorted(sessions.glob("skills-plugin/*/*")):
        listed = (_read_json(root / "manifest.json", warnings) or {}).get("skills") or []
        enabled = {s.get("name"): s.get("enabled") for s in listed if isinstance(s, dict)}
        found += [(d, n, plug, enabled.get(n) if isinstance(enabled.get(n), bool) else None)
                  for d, n, plug in plugin_skills(root, None, "claude.ai", enabled_map, warnings, via="claude.ai")]
    return found


def build_inventory(home, projects=(), app_data=None):
    home = fs_path(home)
    projects = [fs_path(p) for p in projects]
    app_data = fs_path(app_data) if app_data else None
    npx_root = home / ".agents" / "skills"
    warnings = []
    enabled_map = enabled_plugins(home, projects, warnings)

    found = []  # (skill_dir, dir_name, scope, label, plugin, skill_enabled)
    roots = [(home / ".claude" / "skills", "personal", "")]
    roots += [(p / ".claude" / "skills", "project", p.name) for p in projects]
    for skills_dir, scope, label in roots:
        plugin_dirs = _plugin_dirs(skills_dir)
        found += [(d, d.name, scope, label, None, None) for d in _skill_dirs(skills_dir) if d not in plugin_dirs]
        for pdir in plugin_dirs:
            found += [(d, n, "plugin", plug["id"], plug, None)
                      for d, n, plug in plugin_skills(pdir, None, "skills-dir", enabled_map, warnings)]

    for pid, root in installed_plugin_roots(home / ".claude" / "plugins", warnings):
        if not root.is_dir():
            _warn(warnings, root, "plugin_missing", f"El plugin {pid} está registrado pero su carpeta no existe.")
            continue
        mkt = pid.split("@", 1)[1] if "@" in pid else None
        found += [(d, n, "plugin", pid, plug, None)
                  for d, n, plug in plugin_skills(root, pid, mkt, enabled_map, warnings)]

    if app_data:
        found += [(d, n, "plugin", plug["id"], plug, on) for d, n, plug, on in app_skills(app_data, enabled_map, warnings)]

    skills, ids = [], set()
    for skill_dir, dir_name, scope, label, plugin, skill_enabled in found:
        try:
            skill = read_skill(skill_dir / "SKILL.md", dir_name, scope, plugin, warnings, skill_enabled, npx_root)
        except OSError:
            _warn(warnings, skill_dir, "skill_unreadable", "No se pudo leer esta skill.")
            continue
        base = f"{scope}:{label + '/' if label else ''}{dir_name}"
        sid, n = base, 2
        while sid in ids:
            sid, n = f"{base}#{n}", n + 1
        ids.add(sid)
        skills.append({"id": sid, **skill})

    groups = {}
    for s in skills:
        groups.setdefault(s["name"].lower(), []).append(s)
    copy_groups = []
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        kind = "exact" if len({m["sha256"] for m in members}) == 1 else "variants"
        copy_groups.append({"name": key, "kind": kind, "skill_ids": [m["id"] for m in members]})
        for m in members:
            m["copy_group"] = key
    for s in skills:
        s.setdefault("copy_group", None)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estimator": {"method": "chars_per_token", "chars_per_token": CHARS_PER_TOKEN, "estimated": True},
        "sources": {"home": plain(home), "projects": [plain(p) for p in projects],
                    "app_data": plain(app_data) if app_data else None},
        "totals": {
            "skills": len(skills),
            "fixed_tokens": sum(s["tokens"]["fixed"] for s in skills),
            "estimated": True,
        },
        "skills": skills,
        "copy_groups": copy_groups,
        "warnings": warnings,
    }


def write_inventory(inventory, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "inventory.json"
    path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
