# Backpack Skill — Documento de producto del MVP

Versión del 3 de octubre de 2026. Nombre provisional. Documento editable original: https://claude.ai/code/artifact/0c05a472-9c10-448e-9147-446a40488b70

## Resumen y problema

Backpack Skill es una skill con app interactiva que audita, explica y limpia las skills de Claude, pensada para principiantes. El MVP audita, enseña y guía la desinstalación; no instala nada.

Muchos usuarios instalan todas las skills que ven recomendadas en internet. Terminan con cientos de skills que no conocen, que se duplican y que compiten por activarse. Eso tiene tres costos:

- **Contexto:** el nombre y la descripción de cada skill se cargan en todas las conversaciones, aunque nunca se use.
- **Precisión:** con varias skills que prometen lo mismo, Claude puede activar la equivocada o dos a la vez.
- **Seguridad:** muchas skills vienen de repositorios sin revisión y pueden incluir scripts.

Caso de referencia: una instalación real con 367 skills carga unos 53.500 tokens fijos por conversación (estimado).

## Usuario objetivo

Un principiante que instaló skills sin criterio y no sabe qué hace cada una. No sabe qué es un `SKILL.md`, dónde viven los archivos ni cómo se desinstala.

Principios de diseño:

- **Lenguaje sin jerga:** "estas dos hacen lo mismo, quédate con una", nunca "solapamiento semántico del 87%".
- **Asistente inicial de 3 preguntas:** a qué se dedica, qué herramientas usa y qué quiere lograr.
- **Modo simple y modo avanzado:** el simple muestra semáforos y recomendaciones; el avanzado, puntajes, conflictos y el manual completo.
- **Victoria rápida:** en el primer minuto, un resumen del ahorro posible.
- **Sin miedo a romper:** todo cambio se puede deshacer.

## Propuesta: skill como motor, app como cara visible

El usuario instala una sola skill y escribe algo natural, como "revisa mis skills". La skill lee todo lo instalado y genera una app interactiva.

Flujo de la arquitectura:

1. **Skills instaladas** (carpetas con `SKILL.md` de plugins, npx, GitHub o ZIP) y **historial de sesiones** (solo qué skills se usaron, nunca el contenido) alimentan el inventario.
2. **Inventario**: un JSON único con origen, tokens, copias y uso.
3. El inventario alimenta dos piezas en paralelo: el **escáner determinista** (reglas fijas deciden el riesgo, sin juicio de Claude) y **Claude explica** (fichas, recetas, simulador y lenguaje simple).
4. Ambas alimentan la **app interactiva** (Auditoría, Manual, Recetas y Simulador).
5. El usuario decide; las **acciones seguras** (archivar con backup, deshacer, guía para desinstalar) vuelven sobre las skills instaladas solo con confirmación.

Ninguna de las dos piezas sirve sola: una app externa no puede ver qué skills tiene instaladas el usuario, y una skill sola responde con texto que un principiante no sabe interpretar.

## Módulos del MVP

| Módulo | Qué hace | Qué ve el principiante |
| --- | --- | --- |
| Auditor | Mide uso, solapamiento, choques, peso en tokens, procedencia y riesgo de cada skill | Un semáforo y una recomendación: conservar, afinar, fusionar o quitar |
| Manual y recetas | Ficha por skill y cadenas de skills que funcionan juntas, incluidas recetas aplicadas a sus propios proyectos | Un buscador: "quiero cerrar el mes" muestra la receta |
| Simulador de activación | Predice qué skill se activaría ante un pedido escrito y cuáles compiten | Escribe lo que pediría y ve el choque en segundos |
| Acciones seguras | Archivar con backup, deshacer y guía para desinstalar según el origen | Pasos con casillas para marcar lo que ya quitó |

Métricas del auditor:

- **Uso:** invocaciones y última fecha. Solo medible en Claude Code, desde los logs de sesión.
- **Solapamiento:** similitud de descripciones y nombres repetidos entre plugins.
- **Choque:** frases gatillo que compiten y skills que exigen activarse antes de cualquier respuesta.
- **Peso:** tokens de la descripción (costo fijo) y del cuerpo (costo al activarse).
- **Procedencia:** oficial, comunidad conocida o desconocida.
- **Riesgo:** veredicto del escáner de seguridad.

Cada ficha del manual dice qué hace la skill, cómo se activa (comando o frase gatillo), qué necesita, qué entrega y cuándo no usarla.

## Medición de tokens

Backpack Skill muestra el peso antes y después de cada recomendación, siempre marcado como estimación.

- **Costo fijo:** nombre, descripción y ruta de cada skill, cargados en cada conversación. Se mide exacto con el contador de tokens de la API de Anthropic, o se estima sin conexión.
- **Costo variable:** el cuerpo completo del `SKILL.md`, cargado solo al activarse. Una activación equivocada o doble paga ese costo de más.

Instalación de referencia, medida el 3 de octubre de 2026 (estimado, ~3,7 caracteres por token):

| Medida | Valor |
| --- | --- |
| Skills en disco | 367 |
| Costo fijo por conversación | ~53.500 tokens |
| Cuerpo promedio al activarse | ~2.500 tokens |
| Cuerpo más pesado (`_council-engine`) | ~21.000 tokens |
| Copias exactas (mismo nombre) | 20 |
| Ahorro quitando solo copias exactas | ~2.900 tokens (5%) |

Las copias exactas pesan poco. El ahorro grande está en las skills ajenas al trabajo del usuario y en las variantes que hacen lo mismo con otro nombre.

## Seguridad

Backpack Skill es justo el tipo de skill que pedimos no instalar a ciegas, así que debe ser la más transparente.

Principios de la herramienta:

- **Veredicto determinista:** el riesgo lo deciden scripts con reglas fijas, no Claude. Así una skill maliciosa no puede convencer al modelo de marcarla como segura; Claude solo explica.
- **Solo lectura por defecto:** nunca ejecuta los scripts de las skills que analiza.
- **Cambios con confirmación y backup:** archivar antes que borrar, con botón de deshacer.
- **Sin red por defecto:** la consulta a GitHub es opcional y de solo lectura.
- **Historial local:** de las sesiones extrae solo nombres de skills usadas, nunca el contenido.
- **Permisos mínimos:** en Claude Code declara solo las herramientas que necesita.
- **Código pequeño y auditable:** pocas dependencias, `SECURITY.md` y releases con checksums.

Qué busca el escáner:

- Scripts ejecutables y llamadas de red a dominios desconocidos.
- Comandos destructivos como `rm -rf` y texto ofuscado, por ejemplo en base64.
- Acceso a archivos `.env` o credenciales.
- Instrucciones que piden ignorar otras reglas o activarse antes de cualquier respuesta.

La interfaz lo dice claro: el análisis estático reduce el riesgo, pero no garantiza que una skill sea segura.

## Plataformas y limitaciones

La versión completa vive en Claude Code; claude.ai recibe una versión ligera.

| Capacidad | claude.ai | Claude Code |
| --- | --- | --- |
| Ve las skills | Solo las que carga la plataforma | Todas las carpetas, incluidas GitHub y npx |
| Mide uso | No | Sí, desde los logs de sesión |
| Edita o archiva | No, las skills son de solo lectura | Sí, con confirmación |
| Desinstala | Guía paso a paso hacia Configuración | Según el origen, con el comando correcto |
| Dashboard | Foto del momento; se regenera | Puede actualizarse solo |

Procedencia detectada por la huella de cada método:

| Origen | Huella | Cómo se quita |
| --- | --- | --- |
| Plugin (oficial o marketplace de terceros) | Manifiesto del plugin, prefijo `plugin:` | Gestor de plugins |
| `npx skills` | Carpeta en `~/.claude/skills` o `.claude/skills` | El mismo CLI |
| `git clone` manual | Carpeta con `.git` y remoto visible | Borrar la carpeta |
| ZIP subido a claude.ai | Skills de usuario | Configuración |
| Copiada a mano | Sin rastro | Se marca "origen desconocido" |

Una misma skill puede estar en varios agentes (Cursor, Codex, Gemini CLI) y en varios ámbitos (proyecto y global). Backpack Skill agrupa todas las copias y las trata como una sola.

## Distribución

Un repositorio público en GitHub es la fuente única; el código abierto es parte de la seguridad.

| Canal | Cómo llega | Versión |
| --- | --- | --- |
| Claude Code | `/plugin marketplace add usuario/repo` | Completa |
| Otros agentes | `npx skills add usuario/repo` | Completa |
| claude.ai | ZIP en cada release, subido como skill personalizada | Ligera |
| Landing en Vercel | Manual y demo del dashboard con datos de ejemplo | Demo |
| App de escritorio (fase 3) | Binarios firmados en GitHub Releases | Completa |

- **Licencia:** MIT.
- **Catálogo curado (fase 2):** un JSON dentro del repo; la comunidad propone skills por pull request y la revisión queda pública.
- **Instalación por versión fija:** cada skill del catálogo apunta a un commit revisado, no a la última versión.

## Alcance del MVP y fases

El MVP audita, enseña y guía; no edita ni instala nada.

- **Fase 1 · MVP (auditar y enseñar):** inventario y escáner, auditor con semáforos, manual con recetas y "Mis casos", simulador de activación, guía para desinstalar, dashboard interactivo.
- *Puerta 1: validado con principiantes y con claridad sobre qué skills piden.*
- **Fase 2 · Acción (actuar y recomendar):** archivar, fusionar y deshacer en Claude Code; recomendador y catálogo; kits por oficio; chequeo periódico.
- *Puerta 2: comunidad activa en el repo.*
- **Fase 3 · Escritorio (producto para la comunidad):** app con binarios firmados, cambios con un clic, fusión de varias skills en una propia.

## Interfaz

Ver `docs/DISENO.md` y el prototipo: https://claude.ai/artifact/JmwdghhNvNSMSEwJ6GQGBX

## Métricas de éxito

Backpack Skill no tiene telemetría, así que se mide con entrevistas, un reporte opcional que el usuario decide compartir y señales públicas de GitHub.

- **Activación:** usuarios que completan la primera auditoría.
- **Limpieza real:** skills quitadas por usuario y tokens fijos ahorrados.
- **Choques resueltos:** conflictos detectados frente a conflictos resueltos.
- **Uso del manual:** búsquedas y recetas copiadas.
- **Confianza:** reportes de seguridad recibidos y tiempo de respuesta.
- **Comunidad:** estrellas, forks y pull requests al catálogo (fase 2).

Las metas numéricas se fijan después de validar con los primeros usuarios.

## Riesgos y preguntas abiertas

| Riesgo | Mitigación |
| --- | --- |
| Una skill maliciosa manipula el análisis | Veredicto por reglas fijas; el contenido de las skills se trata como datos |
| Falsa sensación de seguridad | Mensaje explícito: el escáner reduce el riesgo, no lo elimina |
| Cambios en cómo Claude carga las skills | Inventario desacoplado y pruebas con cada versión |
| Catálogo desactualizado o comprometido | Llega en fase 2, con versiones fijas por commit y revisión pública |
| El simulador se equivoca | Presentarlo como predicción, no como garantía |
| Sin datos de uso en claude.ai | Recomendar por relevancia, duplicados y choques |

- [ ] Nombre definitivo y si el repo va en español, inglés o ambos.
- [x] Licencia: MIT.
- [ ] ¿El simulador predice con Claude o solo con reglas sobre las descripciones?
- [ ] ¿Quién revisa el catálogo cuando llegue la fase 2?
