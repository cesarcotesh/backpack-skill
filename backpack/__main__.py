import argparse
import json
import sys

from .audit import build_audit, write_audit
from .inventory import build_inventory, write_inventory
from .scanner import scan_inventory, write_scan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m backpack", description="Revisa las skills instaladas de Claude.")
    sub = parser.add_subparsers(dest="command", required=True)
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
    aud.add_argument("--out", default="out", help="Carpeta donde se guarda audit.json.")
    args = parser.parse_args(argv)

    if args.command == "audit":
        with open(args.inventory, encoding="utf-8") as f, open(args.scan, encoding="utf-8") as g:
            result = build_audit(json.load(f), json.load(g))
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
