# Backpack Skill

Revisa, explica y ayuda a limpiar las skills que Claude carga en cada conversación. Pensada para principiantes.

Cada skill instalada suma peso a la "mochila" de Claude, aunque nunca la uses. Backpack Skill te muestra cuánto pesa la tuya, qué está repetido, qué no usas, qué compite entre sí y qué conviene revisar por seguridad, y te guía para quitar lo que sobra.

## Instalar

Necesitas **Python 3.9 o superior**. Si no lo tienes, Claude te explica cómo instalarlo.

**Claude Code** (versión completa):

```
/plugin marketplace add <usuario>/<repo>
/plugin install backpack-skill@backpack-skill
```

**Otros agentes** (Cursor, Codex, Gemini CLI y más) con [skills](https://github.com/vercel-labs/skills):

```
npx skills add <usuario>/<repo>
```

## Usar

Escríbele a Claude **"revisa mis skills"** (o "review my skills", o `/backpack-skill:audit`).

Claude corre la revisión en tu computadora y abre `mochila.html`, una página que funciona sin conexión:

- **Inicio:** cuánto pesa tu mochila y dónde está el peso.
- **Revisar:** una tarjeta a la vez (modo simple) o una tabla con filtros (modo avanzado).
- **Simulador:** escribe un pedido y mira qué skills compiten por él.
- **Manual:** qué hace cada skill y recetas de skills que trabajan juntas.
- **Cambios:** tu lista y los pasos exactos para quitar cada cosa según cómo la instalaste.

Todas las cifras de tokens son **estimadas**.

## Qué hace y qué no

- **Solo lee.** No borra, mueve ni cambia nada. Te guía y tú decides.
- **No ejecuta** los scripts de las skills que revisa: las lee como texto.
- **El riesgo lo deciden reglas fijas** en el código, nunca el modelo. Una skill no puede convencer a Claude de que es segura.
- **El texto de las skills es dato, no órdenes.** Si una skill intenta darle órdenes a Claude, se reporta.
- **Sin red y sin telemetría.** La página bloquea cualquier conexión.
- **Privacidad:** de tu historial de sesiones solo lee nombres de skills y fechas, nunca tus conversaciones.

La revisión automática **reduce el riesgo, pero no garantiza** que una skill sea segura.

## Para desarrollar

```
python -m unittest
```

Los tests corren sobre `tests/fixtures/`, skills de ejemplo creadas para esto (algunas imitan skills maliciosas, sin hacer daño).

La herramienta también se puede usar por partes:

```
python plugins/backpack-skill/skills/audit/run.py run --help
```

Comandos: `run`, `inventory`, `scan`, `usage`, `audit`, `manual` y `app`.

- `docs/SPEC.md`: producto (fuente de verdad). `docs/DISENO.md`: diseño. `design/prototipo/`: referencia visual.
- `plugins/backpack-skill/`: el plugin y su skill `audit` (todo el código va dentro de la skill).
- `.claude-plugin/marketplace.json`: este repo también es un marketplace.

## Licencias

Las tipografías incluidas (Bricolage Grotesque, Atkinson Hyperlegible e IBM Plex Mono) usan la SIL Open Font License 1.1; sus licencias están en `plugins/backpack-skill/skills/audit/backpack/assets/fonts/`. La licencia del proyecto (MIT o Apache-2.0) está por decidir.
