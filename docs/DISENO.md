# Diseño — Backpack Skill

Metáfora: una mochila que Claude carga en cada conversación. Cada skill instalada suma peso, aunque no se use.

Prototipo navegable: https://claude.ai/artifact/JmwdghhNvNSMSEwJ6GQGBX (archivos de referencia en `design/prototipo/`).

## Colores

| Uso | Color |
| --- | --- |
| Fondo | #EEF1EC |
| Superficie (tarjetas) | #FFFFFF |
| Texto principal y botón primario | #16201A |
| Texto secundario | #4C5A51 |
| Bordes y fondos neutros | #D5DDD6, #DCE3DC |
| Quitar / estado activo (naranja de seguridad) | #F2581D, con texto #16201A |
| Repetida / revisar (mostaza) | #E9B425, con texto #16201A; tinte #FBF0CF |
| Conservar (verde pino) | #2E6B4E, con texto #FFFFFF |

El semáforo no depende solo del tono: mostaza (clara), naranja (media) y pino (oscura) también difieren en luminosidad.

## Tipografía

- Títulos y cifras grandes: Bricolage Grotesque, peso 800.
- Texto: Atkinson Hyperlegible (diseñada para máxima legibilidad).
- Nombres de skills: IBM Plex Mono.

## Forma

- Tarjetas grandes con radio 24–28 px; filas con radio 16–18 px; botones en píldora.
- Objetivos táctiles de al menos 44 px.
- Pantalla de celular de referencia: 390 × 844 px.
- Celular (390 × 844 px): navegación inferior con 4 secciones: Revisar, Manual, Simulador, Cambios.
- Escritorio (1280–1440 px): menú lateral oscuro con las mismas 4 secciones, y "Modo avanzado" activo por defecto.
- El diseño es responsivo: el menú lateral pasa arriba y las columnas se apilan en pantallas angostas; la tabla se desplaza dentro de su propia caja.

## Pantallas

1. **Tu mochila**: peso total en tokens y número de skills; lista "Dónde está el peso" (copias exactas, skills que compiten, skills que se cuelan, seguridad); botón "Empezar la revisión".
2. **Revisión por tarjetas**: una skill por tarjeta con etiqueta (Repetida, Choque…), origen, explicación simple, peso fijo, peso al activarse, último uso y sugerencia. Acciones: Quitar, Ver ficha, Conservar, o deslizar. La carga baja en vivo.
3. **Simulador**: el usuario escribe un pedido y ve cuántas y cuáles skills compiten por él, como predicción. Cierra con una sugerencia y "Elegir cuál conservar".
4. **Manual y recetas**: buscador por intención ("cerrar el mes"); receta con pasos numerados, "Cómo pedirlo" con botón Copiar, "Necesita" y "Cuándo no usarla".

5. **Escritorio · Revisar**: menú lateral; encabezado con "Escanear de nuevo" y "Empezar la revisión"; fila de indicadores (carga fija, skills instaladas, copias exactas, skills que se cuelan); tabla "Para revisar" con filtros (Todas, Repetidas, Compiten, Pesadas, Seguridad) y columnas Skill, Motivo, Origen, Peso fijo, Al activarse y Sugerencia; ficha de la skill seleccionada a la derecha con Quitar y Conservar.

## Reglas de contenido

- Lenguaje sin jerga: "estas dos hacen lo mismo, quédate con una".
- Toda cifra de tokens dice que es estimada.
- Lo que no se puede medir en la plataforma actual se dice ("Sin datos aquí"), no se inventa.
