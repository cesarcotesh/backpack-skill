"""Auditor: turns inventory.json + scan.json into a traffic light and one recommendation per skill.

Every decision here is a fixed rule over the two JSON files; no model is asked.
"""
import json
import re
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from .usage import days_since

SCHEMA_VERSION = 1
OVERLAP_MIN = 0.5  # share of description words two skills have in common to "compete"
HEAVY_FIXED = 150  # estimated tokens loaded in every conversation
HEAVY_BODY = 5000  # estimated tokens loaded when the skill activates
UNUSED_DAYS = 30  # last use this long ago is worth mentioning
SCOPE_PRIORITY = {"personal": 0, "project": 1, "plugin": 2}  # which exact copy to keep (personal beats project)
RECOMMENDATION_ORDER = ["remove", "review", "merge", "tune", "keep"]

_WORD = re.compile(r"[a-záéíóúñü0-9]+")
STOPWORDS = set("""
the and for with from that this when use uses using you your are can will into about any all also not only
than then them they their what which who how its it's has have was were been being one two more most other
such some each like just over under via per our out get got make need needs want wants should would could
el la los las un una unos unas de del al en con por para que cuando como este esta estos estas ese esa
sus su tus tu mis mi lo le les se es son ser hay más mas pero sin sobre entre desde hasta cada otro otra
usa usar úsala úsalo skill skills claude
""".split())
# descriptions that try to activate on everything ("se cuelan")
_GREEDY = re.compile(
    r"\b(?:always|must)\s+(?:use|invoke|activate|be\s+used|be\s+invoked)\b|\bbefore\s+(?:any|every)\b|\bproactively\b"
    r"|\b(?:any|every)\s+(?:task|request|conversation|message|question|response|time)s?\b"
    r"|\bsiempre\s+(?:usa|activa|invoca|úsala)|\bantes\s+de\s+cualquier\b|\bcualquier\s+(?:tarea|pedido|conversaci[oó]n|pregunta)\b",
    re.I)


def words(text):
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in STOPWORDS}


def similarity(a, b):
    """Jaccard similarity of two word sets."""
    return len(a & b) / len(a | b) if a and b else 0.0


def _n(number):
    """9394 -> '9.394', as the app shows numbers."""
    return f"{number:,}".replace(",", ".")


def _reason(code, text, related=()):
    return {"code": code, "text": text, "related": list(related)}


def _risk_titles(result, rules):
    return sorted({rules[f["rule"]]["title"] for f in result["findings"] if f["severity"] in ("high", "medium")})


def skill_usage(skills, usage, today=None):
    """{skill id: {count, last_used, days_unused}} from usage.json, or {} without it.
    Logs name a skill by its command ("toolkit:review", "pdf-helper"); a typed short name
    counts for a plugin skill only when nothing else answers to that name."""
    if not usage:
        return {}
    used = usage.get("skills", {})
    plain_names = {s["name"] for s in skills if not s.get("plugin")}
    short = {}
    for s in skills:
        if s.get("plugin") and s["name"] not in plain_names:
            short.setdefault(s["name"], []).append(s["id"])
    out = {}
    for s in skills:
        recs = [used.get(s["command"].lstrip("/"))]
        if short.get(s["name"]) == [s["id"]]:
            recs.append(used.get(s["name"]))
        recs = [r for r in recs if r]
        count = sum(r["count"] for r in recs)
        last = max((r["last_used"] for r in recs), default=None)
        out[s["id"]] = {"count": count, "last_used": last,
                        "days_unused": days_since(last, today) if last else None}
    return out


def build_audit(inventory, scan, usage=None, today=None):
    skills = inventory["skills"]
    use = skill_usage(skills, usage, today)
    since = (usage or {}).get("history_since")
    by_id = {s["id"]: s for s in skills}
    rules = {r["id"]: r for r in scan.get("rules", [])}
    reasons = {s["id"]: [] for s in skills}
    recs = {s["id"]: set() for s in skills}
    name_of = lambda sid: by_id[sid]["command"]

    # copies
    copied = set()
    for group in inventory.get("copy_groups", []):
        ids = group["skill_ids"]
        copied.update(ids)
        if group["kind"] == "exact":
            keeper = min(ids, key=lambda i: (SCOPE_PRIORITY.get(by_id[i]["scope"], 9), i))
            for sid in ids:
                if sid == keeper:
                    reasons[sid].append(_reason("exact_copy_keeper",
                        "Tiene copias exactas en otros lugares. Esta es la que conviene conservar.", [i for i in ids if i != sid]))
                else:
                    reasons[sid].append(_reason("exact_copy_extra",
                        f"Es una copia exacta de {name_of(keeper)}. Puedes quitar esta y quedarte con la otra.", [keeper]))
                    recs[sid].add("remove")
        else:
            for sid in ids:
                others = [i for i in ids if i != sid]
                reasons[sid].append(_reason("same_name_variants",
                    "Hay otra skill con el mismo nombre pero distinto contenido. Elige una o júntalas en una sola.", others))
                recs[sid].add("merge")

    # competing descriptions: only skills Claude can actually pick
    # ponytail: O(n²) pairwise Jaccard; fine for hundreds of skills, index by word if it ever gets slow
    candidates = [s for s in skills if s["flags"]["model_invocable"] and s["flags"]["loaded"]]
    bags = {s["id"]: words(s["description"]) for s in candidates}
    competing = []
    for a, b in combinations(sorted(bags), 2):
        if a in copied and b in copied and by_id[a]["name"].lower() == by_id[b]["name"].lower():
            continue  # already reported as a copy
        sim = similarity(bags[a], bags[b])
        if sim >= OVERLAP_MIN:
            competing.append({"skills": [a, b], "similarity": round(sim, 2)})
    for pair in competing:
        for sid, other in (pair["skills"], pair["skills"][::-1]):
            reasons[sid].append(_reason("competes",
                f"Hace casi lo mismo que {name_of(other)}. Claude puede confundirse entre las dos; quédate con una.", [other]))
            recs[sid].add("merge")

    for s in skills:
        sid = s["id"]
        if s["flags"]["model_invocable"] and s["flags"]["loaded"] and _GREEDY.search(s["description"]):
            reasons[sid].append(_reason("greedy",
                "Su descripción pide usarse siempre o antes de cualquier respuesta, así que se cuela donde no hace falta."))
            recs[sid].add("tune")
        if s["tokens"]["fixed"] >= HEAVY_FIXED:
            reasons[sid].append(_reason("heavy_fixed",
                f"Su descripción es larga: ocupa ~{_n(s['tokens']['fixed'])} tokens en cada conversación (estimado)."))
            recs[sid].add("tune")
        if s["tokens"]["body"] >= HEAVY_BODY:
            reasons[sid].append(_reason("heavy_body",
                f"Al activarse carga ~{_n(s['tokens']['body'])} tokens (estimado)."))
            recs[sid].add("tune")
        if not s["flags"]["loaded"]:
            reasons[sid].append(_reason("disabled", "Está desactivada, así que hoy no pesa."))
        u = use.get(sid)
        if u and u["count"] == 0 and since:
            text = f"No hay registro de uso desde el {since} (hace {days_since(since, today)} días)."
            if s["tokens"]["fixed"] > 0:  # disabled or slash-only skills don't weigh on every conversation
                text += f" Igual ocupa ~{_n(s['tokens']['fixed'])} tokens en cada conversación (estimado); conviene quitarla."
                recs[sid].add("remove")
            reasons[sid].append(_reason("unused", text))
        elif u and u["days_unused"] is not None and u["days_unused"] >= UNUSED_DAYS:
            reasons[sid].append(_reason("unused", f"No la usas hace {u['days_unused']} días."))

        # security of the skill's own folder; the rest of a plugin is judged once, under "plugins"
        result = scan.get("skills", {}).get(sid)
        if result and result.get("self"):
            # the reviewer itself: same findings, told plainly; never suggested for removal
            titles = ", ".join(_risk_titles(result, rules)).lower() or "ninguno"
            reasons[sid] = [_reason("self",
                "Esta es Backpack Skill, la herramienta que hace esta revisión. Sus reglas contienen los patrones "
                f"que buscan ({titles}), por eso aparecen hallazgos. Su código es abierto: puedes revisarlo.")]
            recs[sid] = set()
        elif result and result["risk"] in ("high", "medium"):
            titles = ", ".join(_risk_titles(result, rules)).lower()
            if result["risk"] == "high":
                text = f"La revisión de seguridad encontró algo serio: {titles}. Revísala antes de seguir usándola."
            else:
                text = f"La revisión de seguridad encontró algo para revisar: {titles}."
            reasons[sid].append(_reason(f"security_{result['risk']}", text))
            recs[sid].add("review")

    results, light_totals = {}, {"orange": 0, "mustard": 0, "green": 0}
    for s in skills:
        sid = s["id"]
        rec = min(recs[sid] or {"keep"}, key=RECOMMENDATION_ORDER.index)
        light = "orange" if rec == "remove" else "mustard" if rec != "keep" else "green"
        light_totals[light] += 1
        results[sid] = {"light": light, "recommendation": rec, "reasons": reasons[sid],
                        "tokens": s["tokens"], "usage": use.get(sid)}

    # plugins are what gets uninstalled, so their own files (hooks, servers, commands) are judged here once
    plugins, plugin_lights = {}, {"orange": 0, "mustard": 0, "green": 0}
    members = {}
    for s in skills:
        if s.get("plugin"):
            members.setdefault(s["plugin"]["id"], (s["plugin"], []))[1].append(s)
    for pid, (plugin, plugin_skills) in sorted(members.items()):
        result = scan.get("plugins", {}).get(pid) or {"risk": "none", "findings": []}
        plugin_reasons = []
        if result["risk"] in ("high", "medium"):
            titles = ", ".join(_risk_titles(result, rules)).lower()
            if result["risk"] == "high":
                text = f"Fuera de sus skills, el plugin trae algo serio: {titles}. Revísalo antes de seguir usándolo."
            else:
                text = f"Fuera de sus skills, el plugin trae algo para revisar: {titles}."
            plugin_reasons.append(_reason(f"security_{result['risk']}", text))
        rec = "review" if plugin_reasons else "keep"
        weight = sum(s["tokens"]["fixed"] for s in plugin_skills)
        # a plugin is uninstalled as a whole: suggest it only when none of its skills was used
        if since and weight > 0 and all(use.get(s["id"], {}).get("count") == 0 for s in plugin_skills):
            plugin_reasons.insert(0, _reason("unused",
                f"No usas ninguna de sus {len(plugin_skills)} skills desde el {since}. "
                f"Quitar el plugin libera ~{_n(weight)} tokens en cada conversación (estimado)."))
            rec = "remove"
        light = "orange" if rec == "remove" else "mustard" if rec == "review" else "green"
        plugin_lights[light] += 1
        plugins[pid] = {
            "name": plugin["name"],
            "light": light,
            "recommendation": rec,
            "reasons": plugin_reasons,
            "skill_ids": [s["id"] for s in plugin_skills],
            "fixed_tokens": weight,
            "estimated": True,
        }

    fixed = sum(s["tokens"]["fixed"] for s in skills)
    savings = sum(s["tokens"]["fixed"] for s in skills if results[s["id"]]["recommendation"] == "remove")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {"overlap_min": OVERLAP_MIN, "heavy_fixed": HEAVY_FIXED, "heavy_body": HEAVY_BODY},
        "totals": {
            "skills": len(skills),
            "lights": light_totals,
            "plugin_lights": plugin_lights,
            "fixed_tokens": fixed,
            "fixed_tokens_after_removals": fixed - savings,
            "savings": savings,
            "estimated": True,
            "usage_history_since": since,
            "unused_skills": sum(1 for u in use.values() if u["count"] == 0),
            "unused_fixed_tokens": sum(s["tokens"]["fixed"] for s in skills if use.get(s["id"], {}).get("count") == 0),
        },
        "competing": competing,
        "skills": results,
        "plugins": plugins,
    }


def write_audit(audit, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "audit.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
