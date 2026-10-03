import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

from .app import build_app, write_app
from .audit import _n, build_audit, write_audit
from .inventory import build_inventory, find_app_data, write_inventory
from .manual import build_manual, shortlist, write_manual
from .scanner import scan_inventory, write_scan
from .usage import build_usage, write_usage


def default_out():
    """The plugin's own data folder when installed as a plugin, else ~/.backpack-skill."""
    return Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".backpack-skill")


def load_notes(folder):
    """Claude's explanations (explanations.json), if it wrote them; never required."""
    path = Path(folder) / "explanations.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        print("No se pudo leer explanations.json; la interfaz sale sin explicaciones de Claude.")
        return None


def run(args):
    out = Path(args.out) if args.out else default_out()
    app_data = {"auto": lambda: find_app_data(args.home), "none": lambda: None}.get(args.app_data, lambda: args.app_data)()
    if args.project is None:  # the current folder counts as a project when it has its own .claude
        here = Path.cwd()
        projects = [here] if (here / ".claude").is_dir() and here.resolve() != Path(args.home).resolve() else []
    else:
        projects = args.project
    inventory = build_inventory(args.home, projects, app_data)
    scan = scan_inventory(inventory)
    usage = build_usage(args.home, app_data)
    audit = build_audit(inventory, scan, usage)
    manual = build_manual(inventory, scan, audit)
    for write, data in ((write_inventory, inventory), (write_scan, scan), (write_usage, usage),
                        (write_audit, audit), (write_manual, manual)):
        write(data, out)
    (out / "shortlist.json").write_text(json.dumps(shortlist(inventory, audit, manual), ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    path = write_app(build_app(inventory, scan, audit, manual, load_notes(out)), out)
    t = audit["totals"]
    print(f"Revisé {t['skills']} skills{' (incluye la app de escritorio)' if app_data else ''}.")
    print(f"Carga fija: ~{_n(t['fixed_tokens'])} tokens por conversación (estimado).")
    print(f"Sugerencias: {t['lights']['orange']} para quitar, {t['lights']['mustard']} para revisar, "
          f"{t['lights']['green']} para conservar. Quitando lo sugerido: ~{_n(t['fixed_tokens_after_removals'])} tokens.")
    print(f"Riesgo alto en {scan['totals']['high']} skills y {scan['plugin_totals']['high']} plugins. {scan['disclaimer']}")
    print(f"Interfaz: {path}")
    print(f"Lista para explicar: {out / 'shortlist.json'}")
    if not args.no_open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # Spanish text through pipes on Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m backpack", description="Revisa las skills instaladas de Claude.")
    sub = parser.add_subparsers(dest="command", required=True)
    go = sub.add_parser("run", help="Hace todo: revisa tus skills, arma la interfaz y la abre.")
    go.add_argument("--home", default=str(Path.home()), help="Carpeta que contiene .claude. Por defecto, tu carpeta de usuario.")
    go.add_argument("--app-data", default="auto", help="Carpeta de la app de escritorio de Claude, 'auto' para buscarla o 'none'.")
    go.add_argument("--project", action="append", help="Carpeta de un proyecto. Por defecto, la carpeta actual si tiene .claude.")
    go.add_argument("--out", help="Carpeta de salida. Por defecto, la del plugin o ~/.backpack-skill.")
    go.add_argument("--no-open", action="store_true", help="No abrir la interfaz al terminar.")
    inv = sub.add_parser("inventory", help="Genera inventory.json con las skills encontradas.")
    # --home is required on purpose: nothing reads the real ~/.claude unless asked explicitly
    inv.add_argument("--home", required=True, help="Carpeta que contiene .claude (por ejemplo, tu carpeta de usuario).")
    inv.add_argument("--project", action="append", default=[], help="Carpeta de un proyecto. Se puede repetir.")
    inv.add_argument("--app-data", help="Carpeta de datos de la app de escritorio de Claude "
                                        "(en Windows, %%APPDATA%%\\Claude), para incluir sus plugins y las skills de claude.ai.")
    inv.add_argument("--out", default="out", help="Carpeta donde se guarda inventory.json.")
    scan = sub.add_parser("scan", help="Revisa la seguridad de las skills del inventario y genera scan.json.")
    scan.add_argument("--inventory", default="out/inventory.json", help="Ruta de inventory.json.")
    scan.add_argument("--out", default="out", help="Carpeta donde se guarda scan.json.")
    aud = sub.add_parser("audit", help="Da un semáforo y una recomendación por skill y genera audit.json.")
    aud.add_argument("--inventory", default="out/inventory.json", help="Ruta de inventory.json.")
    aud.add_argument("--scan", default="out/scan.json", help="Ruta de scan.json.")
    aud.add_argument("--usage", help="Ruta de usage.json (opcional).")
    aud.add_argument("--out", default="out", help="Carpeta donde se guarda audit.json.")
    use = sub.add_parser("usage", help="Cuenta qué skills usaste y cuándo, leyendo solo nombres y fechas de los logs.")
    use.add_argument("--home", required=True, help="Carpeta que contiene .claude.")
    use.add_argument("--app-data", help="Carpeta de datos de la app de escritorio de Claude, para incluir sus sesiones.")
    use.add_argument("--out", default="out", help="Carpeta donde se guarda usage.json.")
    man = sub.add_parser("manual", help="Arma una ficha por skill y las recetas, y genera manual.json.")
    man.add_argument("--inventory", default="out/inventory.json", help="Ruta de inventory.json.")
    man.add_argument("--scan", default="out/scan.json", help="Ruta de scan.json.")
    man.add_argument("--audit", default="out/audit.json", help="Ruta de audit.json.")
    man.add_argument("--out", default="out", help="Carpeta donde se guarda manual.json.")
    ui = sub.add_parser("app", help="Arma la interfaz: un único archivo mochila.html con todo adentro.")
    ui.add_argument("--data", default="out", help="Carpeta con inventory, scan, audit y manual (.json).")
    ui.add_argument("--out", default="out", help="Carpeta donde se guarda mochila.html.")
    ui.add_argument("--open", action="store_true", help="Abrir la interfaz al terminar.")
    args = parser.parse_args(argv)

    if args.command == "run":
        return run(args)

    if args.command == "app":
        loaded = []
        for name in ("inventory", "scan", "audit", "manual"):
            with open(f"{args.data}/{name}.json", encoding="utf-8") as f:
                loaded.append(json.load(f))
        notes = load_notes(args.data)
        path = write_app(build_app(*loaded, notes=notes), args.out)
        print(f"Interfaz lista{' con explicaciones de Claude' if notes else ''}: ábrela con doble clic, sin conexión. Guardada en {path}")
        if args.open:
            webbrowser.open(path.resolve().as_uri())
        return 0

    if args.command == "manual":
        loaded = []
        for p in (args.inventory, args.scan, args.audit):
            with open(p, encoding="utf-8") as f:
                loaded.append(json.load(f))
        result = build_manual(*loaded)
        path = write_manual(result, args.out)
        print(f"Manual listo: {len(result['cards'])} fichas y {len(result['recipes'])} recetas.")
        print(f"Guardado en {path}")
        return 0

    if args.command == "usage":
        result = build_usage(args.home, args.app_data)
        path = write_usage(result, args.out)
        print(f"Uso listo: {len(result['skills'])} skills usadas en {result['sources']['files']} sesiones"
              f" (historial desde {result['history_since'] or 'sin datos'}).")
        print(f"Guardado en {path}")
        return 0

    if args.command == "audit":
        usage = None
        if args.usage:
            with open(args.usage, encoding="utf-8") as h:
                usage = json.load(h)
        with open(args.inventory, encoding="utf-8") as f, open(args.scan, encoding="utf-8") as g:
            result = build_audit(json.load(f), json.load(g), usage)
        path = write_audit(result, args.out)
        t = result["totals"]
        print(f"Auditoría lista: {t['lights']['orange']} para quitar, {t['lights']['mustard']} para revisar, "
              f"{t['lights']['green']} para conservar.")
        print(f"Quitando lo sugerido, la carga fija baja de ~{t['fixed_tokens']} a ~{t['fixed_tokens_after_removals']} tokens (estimado).")
        print(f"Guardado en {path}")
        return 0

    if args.command == "scan":
        with open(args.inventory, encoding="utf-8") as f:
            result = scan_inventory(json.load(f))
        path = write_scan(result, args.out)
        t = result["totals"]
        print(f"Revisión lista: {t['high']} con riesgo alto, {t['medium']} medio, {t['low']} bajo, {t['none']} sin hallazgos.")
        p = result["plugin_totals"]
        print(f"Plugins: {p['high']} con riesgo alto, {p['medium']} medio, {p['low']} bajo, {p['none']} sin hallazgos.")
        print(result["disclaimer"])
        print(f"Guardado en {path}")
        return 0

    inventory = build_inventory(args.home, args.project, args.app_data)
    path = write_inventory(inventory, args.out)
    t = inventory["totals"]
    print(f"Inventario listo: {t['skills']} skills, ~{t['fixed_tokens']} tokens fijos por conversación (estimado).")
    if inventory["warnings"]:
        print(f"{len(inventory['warnings'])} aviso(s); revisa la sección 'warnings'.")
    print(f"Guardado en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
