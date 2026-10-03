import argparse
import sys

from .inventory import build_inventory, write_inventory


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m backpack", description="Revisa las skills instaladas de Claude.")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Genera inventory.json con las skills encontradas.")
    # --home is required on purpose: nothing reads the real ~/.claude unless asked explicitly
    inv.add_argument("--home", required=True, help="Carpeta que contiene .claude (por ejemplo, tu carpeta de usuario).")
    inv.add_argument("--project", action="append", default=[], help="Carpeta de un proyecto. Se puede repetir.")
    inv.add_argument("--out", default="out", help="Carpeta donde se guarda inventory.json.")
    args = parser.parse_args(argv)

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
