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
from pathlib import Path

from .audit import STOPWORDS

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
        return "Tu cuenta de claude.ai"
    if o["type"] == "plugin":
        where = "Plugin de la app" if o.get("via") == "app" else "Plugin"
        return f"{where} · {plugin['name']}"
    labels = {"npx-skills": "Instalada con npx", "git": "Clonada con git", "symlink": "Enlace a otra carpeta"}
    scope = "personal" if skill["scope"] == "personal" else "de proyecto"
    return labels.get(o["type"], f"Carpeta {scope}, origen desconocido")


def build_payload(inventory, scan, audit, manual):
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
            "card": {k: c[k] for k in ("what", "activation", "how_to_call", "needs", "when_not",
                                        "usage", "weight", "risk", "recipes", "claude_note")},
        })
    plugins = []
    origins = {s["plugin"]["id"]: origin_label(s) for s in inventory["skills"]
               if s.get("plugin") and s["origin"]["type"] != "claude.ai"}
    for pid, p in audit.get("plugins", {}).items():
        if pid not in origins:
            continue
        plugins.append({"id": pid, "name": p["name"], "origin": origins.get(pid, ""), "light": p["light"],
                        "rec": p["recommendation"], "reasons": [r["text"] for r in p["reasons"]],
                        "skills": p["skill_ids"], "fixed": p["fixed_tokens"]})
    return {
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


def build_app(inventory, scan, audit, manual, fonts_dir=FONTS_DIR):
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__FONTS__*/", font_css(fonts_dir))
    return html.replace("__BACKPACK_DATA__", embed_json(build_payload(inventory, scan, audit, manual)))


def write_app(html, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "mochila.html"
    path.write_text(html, encoding="utf-8")
    return path
