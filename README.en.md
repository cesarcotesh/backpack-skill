# Backpack Skill

*[Leer en español](README.md)*

Reviews, explains and helps you clean up the skills Claude loads in every conversation. Made for beginners.

Every installed skill adds weight to Claude's "backpack", even if you never use it. Backpack Skill shows how heavy yours is, what's duplicated, what you don't use, what overlaps and what deserves a security check, and guides you to remove what you don't need.

## Install

You need **Python 3.9 or later**. If you don't have it, Claude explains how to install it.

**Claude Code** (full version):

```
/plugin marketplace add cesarcotesh/backpack-skill
/plugin install backpack-skill@backpack-skill
```

**Other agents** (Cursor, Codex, Gemini CLI and more) with [skills](https://github.com/vercel-labs/skills):

```
npx skills add cesarcotesh/backpack-skill
```

**claude.ai** (light version): download the zip from the [latest release](https://github.com/cesarcotesh/backpack-skill/releases) and upload it in Customize > Skills.

## Use

Ask Claude to **"review my skills"** (or `/backpack-skill:audit`). The page comes out in English when you write in English.

Claude runs the review on your computer and opens `mochila.html`, a page that works offline:

- **Home:** how heavy your backpack is and where the weight is.
- **Review:** one card at a time (simple mode) or a table with filters (advanced mode).
- **Simulator:** type a request and see which skills compete for it.
- **Manual:** what each skill does, and recipes of skills that work together.
- **Changes:** your list and the exact steps to remove each item, based on how you installed it.

All token figures are **estimates**.

## What it does and doesn't do

- **Read only.** It never deletes, moves or changes anything. It guides; you decide.
- It **never runs** the scripts of the skills it reviews: it reads them as text.
- **Fixed rules in the code decide the risk**, never the model. A skill can't talk Claude into calling it safe.
- **Skill text is data, not orders.** If a skill tries to give Claude orders, it's reported.
- **No network, no telemetry.** The page blocks every connection.
- **Privacy:** from your session history it reads only skill names and dates, never your conversations.

Automated review **lowers the risk, but can't guarantee** a skill is safe. See [SECURITY.md](SECURITY.md).

## Development

```
python -m unittest
python plugins/backpack-skill/skills/audit/run.py run --help
python tools/build_release.py
```

## Licenses

MIT (see `LICENSE`). The bundled fonts (Bricolage Grotesque, Atkinson Hyperlegible, IBM Plex Mono) use the SIL Open Font License 1.1; their licenses are in `plugins/backpack-skill/skills/audit/backpack/assets/fonts/`.
