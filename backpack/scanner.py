"""Deterministic security scanner for skill folders.

Fixed regex rules decide the risk: no model is asked, and nothing written in a
skill can change its own verdict. Files are read as text only and never executed;
symlinks inside a skill are reported, not followed. Static analysis lowers risk,
it does not prove a skill is safe.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .inventory import MAX_READ, fs_path, parse_frontmatter, split_frontmatter

SCHEMA_VERSION = 1
SEVERITY_ORDER = ["none", "low", "medium", "high"]
ALLOWED_DOMAINS = ("github.com", "anthropic.com", "claude.com", "pypi.org", "npmjs.com")
MAX_FILES = 1000  # per skill folder
MAX_FINDINGS = 200  # per skill
DISCLAIMER = "El análisis automático reduce el riesgo, pero no garantiza que una skill sea segura."

# id: (severity, title, explanation). User-facing text in plain Spanish.
RULES = {
    "R01": ("low", "Trae scripts",
            "Incluye archivos de código que se pueden ejecutar. No es malo por sí solo, pero conviene saber qué hacen."),
    "R02": ("medium", "Se conecta a internet",
            "Menciona direcciones o comandos de red hacia sitios que no están en la lista de sitios conocidos."),
    "R03": ("high", "Comandos que borran",
            "Contiene comandos capaces de borrar o dañar archivos de tu equipo."),
    "R04": ("high", "Texto escondido",
            "Tiene texto codificado o caracteres invisibles que ocultan lo que realmente dice."),
    "R05": ("high", "Toca contraseñas o claves",
            "Menciona archivos o variables donde se guardan contraseñas, llaves o claves de acceso."),
    "R06": ("high", "Intenta darle órdenes a Claude",
            "Incluye frases que piden ignorar reglas, activarse siempre, ocultarte cosas o declararse segura."),
    "R07": ("high", "Descarga y ejecuta",
            "Descarga algo de internet y lo ejecuta en un solo paso, sin que puedas revisarlo antes."),
    "R08": ("high", "Ejecuta comandos por su cuenta",
            "Corre comandos en tu equipo de forma automática: al activarse o en ciertos momentos de la sesión, sin que se lo pidas."),
    "R09": ("medium", "Permisos muy amplios",
            "Pide usar la terminal sin restricciones mientras está activa."),
    "R10": ("low", "Archivo que no es texto",
            "Trae un archivo que no se puede leer como texto, así que no se pudo revisar."),
    "R11": ("medium", "Enlace a otro lugar",
            "Trae un enlace que apunta a otra parte de tu equipo. No se siguió."),
    "R12": ("medium", "Arranca programas al abrir Claude",
            "El plugin pone en marcha programas o se conecta a servicios cada vez que abres Claude Code."),
}

# Plugin components that run things on their own (Claude Code docs: plugins-reference)
PLUGIN_COMPONENTS = {"hooks/hooks.json": "R08", "monitors/monitors.json": "R08", ".mcp.json": "R12", ".lsp.json": "R12"}
_RUN_LINE = re.compile(r'"(?:command|url)"\s*:')
_MANIFEST_KEY = re.compile(r'^\s*"(hooks|monitors|mcpServers|lspServers)"\s*:')
_MANIFEST_RULE = {"hooks": "R08", "monitors": "R08", "mcpServers": "R12", "lspServers": "R12"}

_I = re.I
LINE_RULES = [
    ("R03", re.compile(r"\brm\s+-[a-z]*(?:r[a-z]*f|f[a-z]*r)|\bRemove-Item\b.*-Recurse|\b(?:del|erase|rmdir|rd)\b.*\s/[sq]\b"
                       r"|\bmkfs\b|\bdd\s+if=|\bchmod\s+(?:-R\s+)?777\b|\bformat\s+[a-z]:", _I)),
    ("R04", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}|\b(?:eval|exec)\s*\(.*(?:b64decode|atob|base64|fromCharCode)"
                       r"|\bbase64\s+(?:-d|--decode)\b|FromBase64String|[​-‏‪-‮⁠-⁤⁦-⁩]", _I)),
    ("R05", re.compile(r"(?<!\w)\.env\b|\.ssh\b|\bid_(?:rsa|dsa|ecdsa|ed25519)\b|\.aws/credentials|\.netrc\b|\.git-credentials"
                       r"|(?:os\.environ|process\.env|\$env:|getenv)\W*\w*(?:key|token|secret|passw)"
                       r"|\bsecurity\s+find-(?:generic|internet)-password", _I)),
    ("R06", re.compile(r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|other|your)\s+(?:instructions|rules|prompts?)"
                       r"|\bbefore\s+(?:any|every)\s+(?:other\s+)?(?:response|reply|answer)"
                       r"|\bdo\s+not\s+(?:tell|inform|mention\s+to)\s+the\s+user|\bmark\s+(?:this\s+skill\s+|it\s+)?as\s+safe"
                       r"|\bignor(?:a|ar|en)\s+(?:todas\s+)?(?:tus\s+|las\s+|sus\s+)?(?:reglas|instrucciones)"
                       r"|\bantes\s+de\s+cualquier\s+(?:otra\s+)?respuesta|\bno\s+(?:le\s+)?(?:digas|informes|menciones)\s+(?:nada\s+)?al\s+usuario"
                       r"|\bm[aá]rcal[ao]\s+como\s+segur[ao]|\bes\s+segura,?\s+m[aá]rcala", _I)),
    ("R07", re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"
                       r"|\b(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^|\n]*\|\s*(?:iex|Invoke-Expression)\b", _I)),
]
_NET_CMD = re.compile(r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b|\b(?:requests|httpx|aiohttp)\.(?:get|post|put|delete|request)\("
                      r"|\burllib\.request\b|\bfetch\(|\bsocket\.socket\(|\bnew\s+WebSocket\(", _I)
_URL = re.compile(r"https?://(?:[^@/\s]+@)?([A-Za-z0-9.-]+)", _I)
# Injected commands run before Claude reads the skill (docs: skills, "inject dynamic context")
_INJECTED = re.compile(r"!`[^`\n]+`|^\s*```!")
_BROAD_TOOL = re.compile(r"^(?:Bash|PowerShell)(?:\(\*(?::\*)?\))?$")
_TOOL_TOKEN = re.compile(r"[\w-]+(?:\([^)]*\))?")
SCRIPT_EXT = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".psm1",
              ".bat", ".cmd", ".rb", ".pl", ".php", ".vbs"}

_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SECRET_ASSIGN = re.compile(r"(?i)\b([\w-]*(?:key|token|secret|passw\w*)\s*[:=]\s*)(['\"]?)[^\s'\"]+")
_LONG_TOKEN = re.compile(r"(?=[\w+/=-]*\d)(?=[\w+/=-]*[A-Za-z])[\w+/=-]{20,}")


def snippet(line):
    """Short, display-safe excerpt: invisible chars made visible, likely secrets masked."""
    s = _INVISIBLE.sub(lambda m: f"<U+{ord(m.group()):04X}>", line.strip())
    s = _CONTROL.sub("?", s)
    s = re.sub(r"//[^@/\s]+@", "//[oculto]@", s)  # user:password inside a URL
    s = _SECRET_ASSIGN.sub(lambda m: m.group(1) + m.group(2) + "[oculto]", s)
    s = _LONG_TOKEN.sub("[oculto]", s)
    return s[:117] + "..." if len(s) > 120 else s


def _allowed(domain):
    domain = domain.lower().rstrip(".")
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)


def _network(line):
    domains = _URL.findall(line)
    if any(not _allowed(d) for d in domains):
        return True
    return bool(_NET_CMD.search(line)) and not domains  # a command pointed only at known sites is fine


def _tool_tokens(value):
    items = value if isinstance(value, list) else [value or ""]
    return [t for item in items for t in _TOOL_TOKEN.findall(str(item))]


class _Scan:
    def __init__(self):
        self.findings = {}

    def add(self, rule, file, line, text=""):
        self.findings.setdefault((file, line or 0, rule), {
            "rule": rule, "severity": RULES[rule][0], "file": file, "line": line, "snippet": snippet(text)})

    def scan_text(self, rel, text, is_skill_md):
        lines = text.splitlines()
        is_script = (Path(rel).suffix.lower() in SCRIPT_EXT or rel.startswith("bin/")  # plugin bin/ is on the Bash PATH
                     or bool(lines and lines[0].startswith("#!")))
        if is_script:
            self.add("R01", rel, 1, lines[0] if lines else "")
        component = PLUGIN_COMPONENTS.get(rel)
        if component:
            run_lines = [(no, line) for no, line in enumerate(lines, 1) if _RUN_LINE.search(line)]
            for no, line in run_lines or [(1, lines[0] if lines else "")]:
                self.add(component, rel, no, line)
        if rel == ".claude-plugin/plugin.json":
            for no, line in enumerate(lines, 1):
                m = _MANIFEST_KEY.match(line)
                if m:
                    self.add(_MANIFEST_RULE[m.group(1)], rel, no, line)
        for no, line in enumerate(lines, 1):
            for rule, rx in LINE_RULES:
                if rx.search(line):
                    self.add(rule, rel, no, line)
            # outside scripts a bare link is just documentation; only commands that reach out count
            if _network(line) and (is_script or _NET_CMD.search(line)):
                self.add("R02", rel, no, line)
            if is_skill_md and _INJECTED.search(line):
                self.add("R08", rel, no, line)
        if is_skill_md:
            self.scan_frontmatter(rel, text, lines)

    def scan_frontmatter(self, rel, text, lines):
        fm_lines, _, _ = split_frontmatter(text)
        if fm_lines is None:
            return
        fm, _ = parse_frontmatter(fm_lines)
        key_line = {}
        for no, line in enumerate(lines[1:len(fm_lines) + 1], 2):
            m = re.match(r"([A-Za-z0-9_-]+):", line)
            if m:
                key_line.setdefault(m.group(1), (no, line))
        if "hooks" in fm:
            self.add("R08", rel, *key_line["hooks"])
        if any(_BROAD_TOOL.match(t) for t in _tool_tokens(fm.get("allowed-tools"))):
            self.add("R09", rel, *key_line["allowed-tools"])


def scan_skill(skill_dir):
    """Scan one skill folder. Returns {"risk", "findings", "truncated"}."""
    return _scan_folder(fs_path(skill_dir))


def scan_plugin(plugin_root):
    """Scan a plugin's own files (hooks, MCP/LSP servers, bin/, commands, agents...).
    Its skills/ folder is left out: each skill there is scanned on its own."""
    return _scan_folder(fs_path(plugin_root), skip_top={"skills"})


def _scan_folder(skill_dir, skip_top=frozenset()):
    scan, count, truncated = _Scan(), 0, False
    for dirpath, dirnames, filenames in os.walk(skill_dir):  # followlinks=False: linked dirs are not entered
        here = Path(dirpath)
        for d in sorted(dirnames):
            if (here / d).is_symlink():
                scan.add("R11", (here / d).relative_to(skill_dir).as_posix(), None)
        dirnames[:] = sorted(d for d in dirnames if d != ".git" and not (here / d).is_symlink()
                             and not (here == skill_dir and d in skip_top))
        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(skill_dir).as_posix()
            count += 1
            if count > MAX_FILES:
                truncated = True
                break
            if path.is_symlink():  # could point at ~/.ssh; never read through it
                scan.add("R11", rel, None)
                continue
            with open(path, "rb") as f:
                raw = f.read(MAX_READ)
            if b"\x00" in raw[:8192]:
                scan.add("R10", rel, None)
                continue
            scan.scan_text(rel, raw.decode("utf-8-sig", errors="replace"), rel == "SKILL.md")
        if truncated:
            break
    findings = [scan.findings[k] for k in sorted(scan.findings)]
    if len(findings) > MAX_FINDINGS:
        findings, truncated = findings[:MAX_FINDINGS], True
    risk = max((f["severity"] for f in findings), key=SEVERITY_ORDER.index, default="none")
    return {"risk": risk, "findings": findings, "truncated": truncated}


def scan_inventory(inventory):
    results, warnings, by_dir = {}, [], {}
    for skill in inventory["skills"]:
        skill_dir = Path(skill["path"]).parent
        if not skill_dir.is_dir():
            warnings.append({"path": str(skill_dir), "code": "skill_missing",
                             "message": "La carpeta de esta skill ya no existe."})
            continue
        if skill_dir not in by_dir:
            try:
                by_dir[skill_dir] = scan_skill(skill_dir)
            except OSError:
                warnings.append({"path": str(skill_dir), "code": "skill_unreadable",
                                 "message": "No se pudo revisar esta skill."})
                continue
        results[skill["id"]] = by_dir[skill_dir]

    plugins = {}
    roots = {s["plugin"]["id"]: Path(s["plugin"]["root"]) for s in inventory["skills"] if s.get("plugin")}
    for pid, root in sorted(roots.items()):
        try:
            plugins[pid] = scan_plugin(root)
        except OSError:
            warnings.append({"path": str(root), "code": "plugin_unreadable", "message": "No se pudo revisar este plugin."})

    def count(items):
        totals = {level: 0 for level in SEVERITY_ORDER}
        for r in items.values():
            totals[r["risk"]] += 1
        return totals

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "allowed_domains": list(ALLOWED_DOMAINS),
        "rules": [{"id": k, "severity": v[0], "title": v[1], "explanation": v[2]} for k, v in RULES.items()],
        "totals": count(results),
        "plugin_totals": count(plugins),
        "skills": results,
        "plugins": plugins,
        "warnings": warnings,
    }


def write_scan(scan, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "scan.json"
    path.write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
