# Seguridad / Security

*English below.*

Backpack Skill revisa skills de terceros, así que tiene que ser la más transparente de todas.

## Cómo reportar un problema

**No abras un issue público** para un problema de seguridad. Usa el reporte privado de GitHub:
pestaña **Security** del repositorio → **Report a vulnerability**. Respondemos lo antes posible y publicamos la corrección con un aviso.

## Qué garantiza el diseño

- **Solo lectura.** No borra, mueve ni modifica skills, plugins ni configuraciones. Solo escribe en su propia carpeta de salida.
- **No ejecuta** nada de las skills que revisa: las lee como texto. Los enlaces dentro de una skill no se siguen.
- **El riesgo lo deciden reglas fijas** (`scanner.py`), con tests. El modelo nunca decide un veredicto, y el texto de una skill no puede cambiar el suyo.
- **Sin red y sin telemetría.** El código no importa módulos de red ni de procesos (un test lo verifica), y la página generada bloquea cualquier conexión con su política de seguridad (CSP).
- **Privacidad:** del historial de sesiones solo se extraen nombres de skills y fechas. Las rutas en la página usan `~` en lugar de tu carpeta de usuario.
- **Sin dependencias:** solo la biblioteca estándar de Python.

## Qué no garantiza

El análisis estático **reduce el riesgo, pero no garantiza** que una skill sea segura: puede haber falsos positivos (una skill que solo *advierte* contra `rm -rf`) y falsos negativos (código malicioso escrito de una forma que las reglas no conocen).

Backpack Skill se reconoce a sí misma solo por la carpeta desde la que corre, nunca por su contenido, así que una copia o un impostor reciben el veredicto normal.

## Verificar un release

Cada release trae el zip de la skill y `SHA256SUMS.txt`. El zip es reproducible: puedes reconstruirlo desde el código etiquetado con `python tools/build_release.py` y comparar.

```
sha256sum -c SHA256SUMS.txt
```

En Windows (PowerShell): `Get-FileHash backpack-skill-audit-<versión>.zip -Algorithm SHA256`.

---

## Reporting a vulnerability

**Please don't open a public issue.** Use GitHub's private reporting: the repository's **Security** tab → **Report a vulnerability**.

## What the design guarantees

- **Read only.** It never deletes, moves or changes skills, plugins or settings; it only writes to its own output folder.
- **Nothing from the reviewed skills is executed**; files are read as text and links inside a skill are not followed.
- **Fixed, tested rules decide the risk** (`scanner.py`). The model never decides a verdict, and a skill's own text can't change it.
- **No network, no telemetry.** The code imports no network or process modules (tested), and the generated page blocks every connection with its Content Security Policy.
- **Privacy:** only skill names and dates are read from session logs. Paths on the page use `~` instead of your user folder.
- **No dependencies:** Python standard library only.

## What it doesn't guarantee

Static analysis **lowers the risk but can't guarantee** a skill is safe: expect false positives and false negatives. Backpack Skill recognizes itself only by the folder it runs from, never by content, so a copy or an impostor gets the normal verdict.

## Verifying a release

Each release ships the skill zip and `SHA256SUMS.txt`. The zip is reproducible: rebuild it from the tagged source with `python tools/build_release.py` and compare. Check it with `sha256sum -c SHA256SUMS.txt` (or `Get-FileHash` on Windows).
