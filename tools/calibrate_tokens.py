"""Compare our token estimate with Claude Code's own (`claude plugin details`) and suggest calibration.

    python tools/calibrate_tokens.py out/inventory.json

Needs the `claude` CLI. Offline: Claude Code measures each plugin folder locally (--plugin-dir),
nothing is installed and no API is called. Dev tool only; it is not shipped with the skill.
"""
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path


def number(text):
    text = text.strip().lstrip("~").replace(",", "")
    return float(text[:-1]) * 1000 if text.endswith("k") else float(text)


def measure(root, name):
    """{component: (always_on, on_invoke)} as Claude Code reports them (rounded)."""
    out = subprocess.run(["claude", "--plugin-dir", root, "plugin", "details", name], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=120).stdout
    rows = re.findall(r"^\s*(\S+)\s+(~[\d.,]+k?)\s+(~[\d.,]+k?)\s*$", out, re.M)
    return {comp: (number(a), number(b)) for comp, a, b in rows}


def main(inventory_path):
    inv = json.load(open(inventory_path, encoding="utf-8"))
    plugins = {}
    for s in inv["skills"]:
        if s.get("plugin"):
            plugins.setdefault(s["plugin"]["root"], (s["plugin"]["name"], {}))[1][s["name"]] = s
    for pid, extra in inv.get("plugin_extras", {}).items():  # plugins with agents/commands but no skills
        plugins.setdefault(extra["plugin"]["root"], (extra["plugin"]["name"], {}))
    # Claude Code labels agents by file name here, though they are invoked by their header name
    ours_extra = {(e["plugin"]["root"], key): i["fixed"] for e in inv.get("plugin_extras", {}).values()
                  for i in e["items"] for key in (i["name"], Path(i["path"]).stem)}
    listing, body, extras, unmatched = [], [], [], 0.0
    for root, (name, skills) in sorted(plugins.items()):
        for comp, (always, invoke) in measure(root, name).items():
            s = skills.get(comp)
            if not s:
                if (root, comp) in ours_extra:
                    extras.append((ours_extra[(root, comp)], always))  # agents and commands
                else:
                    unmatched += always
                continue
            if s["flags"]["model_invocable"]:
                chars = len(s["name"]) + 2 + len((s["description"] + (" " + s["when_to_use"] if s.get("when_to_use") else ""))[:1536])
                listing.append((chars, always))
            if s["tokens"]["body"]:
                body.append((s["tokens"]["body"] * inv["estimator"]["body"], invoke))  # back to characters
    ratio = lambda pairs: sum(c for c, _ in pairs) / sum(t for _, t in pairs)
    k = ratio(listing)
    mae = statistics.mean(abs(c / k - t) for c, t in listing)
    print(f"skills compared: {len(listing)}")
    print(f"listing: {k:.2f} chars/token (mean error {mae:.1f} tokens per skill; Claude Code rounds to 10)")
    print(f"body:    {ratio(body):.2f} chars/token over {len(body)} skills")
    ours, theirs = sum(o for o, _ in extras), sum(t for _, t in extras)
    print(f"agents/commands: {len(extras)} matched, ours ~{ours:.0f} vs Claude Code ~{theirs:.0f} tokens"
          f" (mean error {statistics.mean(abs(o - t) for o, t in extras) if extras else 0:.1f})")
    print(f"components Claude Code counts that we don't: ~{unmatched:.0f} tokens")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/inventory.json")
