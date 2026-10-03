import argparse
import json
import sys

from .inventory import build_inventory, write_inventory
from .scanner import scan_inventory, write_scan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m backpack", description="Revisa las skills instaladas de Claude.")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Genera inventory.json con las skills encontradas.")
    # --home is required on purpose: nothing reads the real ~/.claude unless asked explicitly
    inv.add_argument("--home", required=True, help="Carpeta que contiene .claude (por ejemplo, tu carpeta de usuario).")
    inv.add_argument("--project", action="append", default=[], help="Carpeta de un proyecto. Se puede repetir.")
    inv.add_argument("--out", default="out", help="Carpeta donde se guarda inventory.json.")
    scan = sub.add_parser("scan", help="Revisa la seguridad de las skills del inventario y genera scan.json.")
    scan.add_argument("--inventory", default="out/inventory.json", help="Ruta de inventory.json.")
    scan.add_argument("--out", default="out", help="Carpeta donde se guarda scan.json.")
    args = parser.parse_args(argv)

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

    inventory = build_inventory(args.home, args.project)
    path = write_inventory(inventory, args.out)
    t = inventory["totals"]
    print(f"Inventario listo: {t['skills']} skills, ~{t['fixed_tokens']} tokens fijos por conversación (estimado).")
    if inventory["warnings"]:
        print(f"{len(inventory['warnings'])} aviso(s); revisa la sección 'warnings'.")
    print(f"Guardado en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
