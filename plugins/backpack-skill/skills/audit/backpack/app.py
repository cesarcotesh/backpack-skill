"""Builds the single-file app: app_template.html + the four JSON files, embedded.

The data goes inside the page because a file opened from disk can't read other local
files. It sits in a non-executable <script type="application/json"> block with "<"
escaped, so skill text can't close the tag; the page only ever shows it as text
(textContent, never innerHTML) and its CSP blocks every network request.
Fonts are embedded from backpack/assets/fonts/*.woff2 when present; otherwise the
page falls back to system fonts.
"""
import base64
import json
import re
from pathlib import Path

from .audit import STOPWORDS
from .i18n import lang, t
from .inventory import plain

TEMPLATE = Path(__file__).with_name("app_template.html")
FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
# file name -> (family, weight or weight range); Google Fonts "latin" subsets, SIL OFL 1.1
FONT_FILES = {
    "bricolage-grotesque.woff2": ("Bricolage Grotesque", "600 800"),  # variable font: one file, both weights
    "atkinson-hyperlegible-400.woff2": ("Atkinson Hyperlegible", 400),
    "atkinson-hyperlegible-700.woff2": ("Atkinson Hyperlegible", 700),
    "ibm-plex-mono-500.woff2": ("IBM Plex Mono", 500),
    "ibm-plex-mono-600.woff2": ("IBM Plex Mono", 600),
}


def origin_label(skill):
    o, plugin = skill["origin"], skill.get("plugin")
    if o["type"] == "claude.ai":
        return t("origin.claude_ai")
    if o["type"] == "platform":
        return t("origin.platform")
    if o["type"] == "plugin":
        return t("origin.app_plugin" if o.get("via") == "app" else "origin.plugin", name=plugin["name"])
    labels = {"npx-skills": "origin.npx", "git": "origin.git", "symlink": "origin.symlink"}
    return t(labels.get(o["type"], "origin.unknown_personal" if skill["scope"] == "personal" else "origin.unknown_project"))


def home_path(path, home):
    """'~/…' form: no user name on the page, and it still works in a terminal."""
    p = plain(path).replace("\\", "/")
    for base in (home, Path.home()):  # a project can live outside the analyzed home but inside yours
        h = plain(base).replace("\\", "/").rstrip("/")
        if p.lower().startswith(h.lower() + "/"):
            return "~" + p[len(h):]
    return p


def guide(skill, home):
    """How to uninstall, by origin (sources: Claude Code plugin CLI docs, claude.ai and Claude
    help center, vercel-labs/skills README). The MVP only guides; it never deletes."""
    o, plugin = skill["origin"], skill.get("plugin") or {}
    folder = home_path(Path(plain(skill["path"])).parent, home)
    if o["type"] == "claude.ai":
        return {"how": t("guide.claude_ai", name=skill["name"]), "command": None}
    if o["type"] == "platform":
        return {"how": t("guide.platform"), "command": None}
    if o["type"] == "plugin" and o.get("via") == "app":
        return {"how": t("guide.app_plugin", name=plugin["name"]), "command": None}
    if o["type"] == "plugin" and plugin.get("marketplace") == "skills-dir":
        return {"how": t("guide.skills_dir_plugin"),
                "command": None, "path": home_path(plugin["root"], home)}
    if o["type"] == "plugin":
        scope = plugin.get("install_scope")
        flag = f" --scope {scope}" if scope in ("project", "local") else ""
        return {"how": t("guide.cc_plugin"),
                "command": f"claude plugin uninstall {plugin['id']}{flag}"}
    if o["type"] == "npx-skills":
        where = "--global " if skill["scope"] == "personal" else ""
        return {"how": t("guide.npx"),
                "command": f"npx skills remove {where}{Path(plain(skill['path'])).parent.name}"}
    if o["type"] == "symlink":
        return {"how": t("guide.symlink"),
                "command": None, "path": folder}
    return {"how": t("guide.folder"), "command": None, "path": folder}


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069]")


def clean_notes(notes, ids, limit=600):
    """Claude's explanations, kept only for known skills, as short plain text."""
    out = {}
    for sid, text in (notes or {}).items() if isinstance(notes, dict) else []:
        if sid in ids and isinstance(text, str) and text.strip():
            out[sid] = _CONTROL.sub(" ", text.strip())[:limit]
    return out


def build_payload(inventory, scan, audit, manual, notes=None):
    home = inventory.get("sources", {}).get("home", "")
    notes = clean_notes(notes, {s["id"] for s in inventory["skills"]})
    skills = []
    for s in inventory["skills"]:
        a, c = audit["skills"][s["id"]], manual["cards"][s["id"]]
        # claude.ai skills are turned off one by one in its settings; real plugins go as a whole
        whole_plugin = bool(s.get("plugin")) and s["origin"]["type"] != "claude.ai"
        skills.append({
            "id": s["id"],
            "name": s["name"],
            "command": s["command"],
            "origin": origin_label(s),
            "plugin": s["plugin"]["id"] if whole_plugin else None,
            "description": s["description"],
            "triggers": s.get("when_to_use"),
            "invocable": s["flags"]["model_invocable"] and s["flags"]["loaded"],
            "light": a["light"],
            "rec": a["recommendation"],
            "codes": [r["code"] for r in a["reasons"]],
            "reasons": [r["text"] for r in a["reasons"]],
            "fixed": s["tokens"]["fixed"],
            "body": s["tokens"]["body"],
            "usage": a.get("usage"),
            "risk": scan.get("skills", {}).get(s["id"], {}).get("risk", "none"),
            "card": {**{k: c[k] for k in ("what", "activation", "how_to_call", "needs", "when_not",
                                           "usage", "weight", "risk", "recipes")},
                     "claude_note": notes.get(s["id"]) or c.get("claude_note")},
            "guide": None if whole_plugin else guide(s, home),
        })
    plugins = []
    first = {}
    for s in inventory["skills"]:
        if s.get("plugin") and s["origin"]["type"] != "claude.ai":
            first.setdefault(s["plugin"]["id"], s)
    for pid, extra in inventory.get("plugin_extras", {}).items():  # plugins with agents/commands but no skills
        plug = extra["plugin"]
        if pid not in first and plug.get("via") != "claude.ai":
            origin = {"type": "plugin", "marketplace": plug["marketplace"], **({"via": plug["via"]} if plug.get("via") else {})}
            first[pid] = {"name": plug["name"], "scope": "plugin", "origin": origin, "plugin": plug,
                          "path": str(Path(plain(plug["root"])) / "plugin")}
    for pid, p in audit.get("plugins", {}).items():
        if pid not in first:
            continue
        plugins.append({"id": pid, "name": p["name"], "origin": origin_label(first[pid]), "light": p["light"],
                        "rec": p["recommendation"], "reasons": [r["text"] for r in p["reasons"]],
                        "skills": p["skill_ids"], "fixed": p["fixed_tokens"], "guide": guide(first[pid], home),
                        "extras": p.get("extras", {"agents": 0, "commands": 0, "fixed": 0})})
    return {
        "lang": lang(),
        "generated_at": audit["generated_at"],
        "totals": audit["totals"],
        "competing": audit.get("competing", []),
        "disclaimer": scan.get("disclaimer", ""),
        "skills": skills,
        "plugins": plugins,
        "recipes": manual.get("recipes", []),
        "stopwords": sorted(STOPWORDS),
    }


def font_css(fonts_dir=FONTS_DIR):
    rules = []
    for name, (family, weight) in FONT_FILES.items():
        path = fonts_dir / name
        if path.is_file():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            rules.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
                         f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "\n".join(rules)


def embed_json(data):
    """JSON safe inside an HTML <script> block: no '<' can start a closing tag."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def build_app(inventory, scan, audit, manual, notes=None, fonts_dir=FONTS_DIR):
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__FONTS__*/", font_css(fonts_dir))
    return html.replace("__BACKPACK_DATA__", embed_json(build_payload(inventory, scan, audit, manual, notes)))


def write_app(html, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "mochila.html"
    path.write_text(html, encoding="utf-8")
    return path
