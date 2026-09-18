# Tidal Extractor — Design System

**Estado:** fuente de verdad visual para el rework de la interfaz  
**Dirección:** minimalismo editorial, oscuro y audiophile; inspirado en la claridad de Apple Music sin copiar su marca ni sus componentes.  
**Referencia principal:** proyecto Stitch [Tidal Music Downloader UI](https://stitch.withgoogle.com/projects/5324288617561675250?pli=1).

## 1. Objetivo

Tidal Extractor debe sentirse como un espacio de trabajo musical confiable: rápido para encontrar contenido, claro para extraerlo y tranquilo mientras una descarga está en curso. La interfaz debe priorizar el contenido y las decisiones importantes, no adornos visuales.

### Principios

1. **Contenido primero.** Portadas, títulos, artistas, calidad y progreso tienen más peso que la decoración.
2. **Una jerarquía por pantalla.** Cada vista tiene una acción primaria evidente y acciones secundarias discretas.
3. **Precisión audiophile.** Metadatos técnicos usan una lectura compacta y monoespaciada; el estado de calidad nunca depende solo del color.
4. **Capas tonales.** La profundidad se crea con superficies y divisores sutiles, no con sombras pesadas, glassmorphism o gradientes permanentes.
5. **Feedback persistente.** La cola y el progreso deben poder consultarse sin perder el contexto de búsqueda o biblioteca.
6. **Accesible por defecto.** Teclado, foco visible, lectura semántica, contraste y reduced motion son parte del diseño, no una fase posterior.

## 2. Alcance y decisiones

Este documento define la dirección visual y la distribución para el frontend actual. El rework conserva el modelo de pestañas existente (`search`, `queue`, `history`, `stats`), la lógica de autenticación y la API/WebSocket de descargas.

- La barra lateral izquierda de Stitch es la referencia de densidad e información. En la implementación actual se adapta a una navegación superior compacta para conservar el estado de pestañas, simplificar el uso en pantallas pequeñas y evitar introducir un router para este cambio.
- El reproductor permanece fijo en la parte inferior.
- Actividad de descargas y preferencias son superficies contextuales: panel lateral en escritorio y sheet inferior en móvil.
- La copia visible actual permanece en inglés para respetar el contrato existente de la app. El idioma del producto y el idioma preferido de subtítulos son decisiones independientes.
- El código HTML exportado por Stitch es material de referencia, no un componente de producción: usa Tailwind CDN, fuentes externas y datos estáticos.

## 3. Tokens visuales

Los nombres conceptuales deben mantenerse estables aunque cambie el valor. Los alias existentes de `frontend/src/index.css` (`--obsidian`, `--graphite`, `--slate`, `--porcelain`, `--silver`, `--mint`) representan estas mismas funciones.

### Color

| Token conceptual | Valor de referencia | Uso |
|---|---|---|
| Canvas / Obsidian | `#0A0A0B` | Fondo global |
| Surface / Graphite | `#121214` | Cards, navegación y controles |
| Surface elevated | `#18181B` | Paneles, filas activas y overlays |
| Surface highest / Slate | `#27272A` | Hover, selección y controles elevados |
| Border subtle | `rgba(255, 255, 255, .08)` | Divisores y contornos discretos |
| Border strong | `rgba(255, 255, 255, .14)` | Inputs y superficies interactivas |
| Text primary | `#FAFAFA` | Títulos y acciones principales |
| Text secondary | `#A1A1AA` | Artista, metadatos y ayuda |
| Text tertiary | `#71717A` | Etiquetas auxiliares y estados inactivos |
| Text disabled | `#3F3F46` | Elementos no disponibles |
| Accent primary | `#FFFFFF` | CTA principal, foco y progreso principal |
| Accent soft | `#E4E4E7` | Estados seleccionados y controles secundarios |
| Brand / success | `#8DE7D5` | Conexión, éxito y señal positiva; uso escaso |
| Warning | `#F2C572` | Advertencias recuperables |
| Danger | `#E11D48` | Error, cancelación destructiva y clipping |

Reglas de color:

- El 80–90 % de la superficie debe ser neutral. El mint y el crimson son semánticos, no decoración.
- No usar gradientes para fondos, botones o marca. Una excepción controlada es la visualización técnica del reproductor si comunica estado de reproducción.
- No usar color como único indicador: acompañar estados con texto, icono o `aria-label`.
- Mantener al menos 4.5:1 para texto normal y 3:1 para texto grande o elementos gráficos esenciales.

### Tipografía

- **UI:** Geist cuando esté disponible; fallback `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
- **Datos técnicos:** JetBrains Mono para calidad, duración, BPM, tonalidad, tamaño, progreso y números de pista.
- **Escala:**

  | Rol | Tamaño / altura de línea |
  |---|---|
  | Display de vista | `32 / 38 px` |
  | Título de sección | `22 / 28 px` |
  | Título de card o álbum | `16 / 22 px` |
  | Cuerpo principal | `14–16 / 20–24 px` |
  | Metadato | `12–13 / 18 px` |
  | Etiqueta técnica | `11–12 / 16 px` |

- Peso alto solo para título, estado o CTA. Los metadatos deben respirar y no competir con el nombre de la obra.
- Evitar texto en mayúsculas sostenidas salvo labels técnicos cortos.

### Forma, espacio y profundidad

- Radio base: `8 px` para controles y `12 px` para superficies grandes; usar `4 px` únicamente para badges densos.
- Espaciado base: múltiplos de `4 px`; preferir `8`, `12`, `16`, `24`, `32` y `48 px`.
- Divisores de `1 px`, con baja opacidad. No encerrar cada elemento en una card.
- La profundidad proviene de una superficie ligeramente más clara y un borde sutil; evitar sombras difusas grandes.
- Áreas táctiles mínimas: `44 × 44 px`.

## 4. Shell y distribución

### Escritorio (>= 1280 px)

- Contenedor de contenido: máximo aproximado de `1280 px`, centrado.
- Márgenes laterales: `32–48 px`; gutters internos: `16–32 px`.
- Shell vertical: navegación superior → contenido desplazable → reproductor fijo.
- La actividad de descargas y ajustes se abre como panel lateral sin cambiar la ruta ni perder filtros.
- El reproductor reserva espacio inferior para que la última fila nunca quede oculta.

### Tablet (768–1279 px)

- Reducir márgenes a `24 px` y pasar grids de cuatro a dos columnas.
- Mantener la navegación horizontal con etiquetas; ocultar solo texto no esencial, nunca acciones sin alternativa accesible.
- Los paneles pueden ocupar hasta `min(520px, 100vw)`.

### Móvil (< 768 px)

- Una columna, padding de `16 px` y navegación horizontal desplazable.
- El reproductor se convierte en una barra compacta; controles secundarios viven en el sheet.
- El sheet de actividad ocupa la pantalla disponible y respeta `env(safe-area-inset-bottom)`.
- Tablas se convierten en filas apiladas; la acción principal permanece visible.
- No depender de hover. Todo debe funcionar con toque, teclado o lector de pantalla.

## 5. Arquitectura de información

### Navegación principal

Orden recomendado:

1. **Search** — descubrir pistas, álbumes y playlists.
2. **Queue** — revisar descargas activas, fallidas y completadas.
3. **History** — consultar actividad pasada.
4. **Stats** — observar métricas sin mezclarlas con acciones de extracción.

Acciones persistentes del shell:

- estado de conexión en vivo;
- contador de cola;
- panel de actividad;
- preferencias;
- perfil o sesión.

La pestaña activa debe tener `aria-current="page"` y una señal visual de alto contraste.

## 6. Especificación por pantalla

### Search — Explorador y extractor

**Objetivo:** pasar de búsqueda a extracción sin ambigüedad.

- Encabezado corto con título, contexto y una sola frase de ayuda.
- Input de búsqueda como foco principal; permitir pegar una URL y detectarla sin un modo separado.
- Selector segmentado para `Tracks`, `Albums` y `Playlists`.
- `Refine` agrupa filtros avanzados y no compite con el input.
- Resultados en filas con portada, título, artista, álbum, duración, calidad y acción.
- Los resultados de álbum muestran un contexto editorial: portada grande, título, artista, año y acción primaria.
- La acción de extracción debe decir qué ocurrirá (`Add to queue`, `Download`, etc.); no usar iconos ambiguos como única etiqueta.
- Los badges técnicos usan JetBrains Mono y texto legible: `LOSSLESS`, `HI-RES`, duración, bitrate o formato.
- Cover fallbacks deben ser iconos SVG o superficies neutras, nunca emojis o caracteres decorativos como estructura.

### Queue — Cola y monitoreo

**Objetivo:** responder rápidamente “qué está pasando y qué puedo hacer”.

- Primero: resumen de activas, fallidas, completadas y velocidad/progreso.
- Descargas activas muestran nombre, contexto, porcentaje, barra, tamaño y acción de cancelar.
- El progreso persistente vive en la actividad; los toasts solo anuncian cambios importantes.
- Fallos muestran causa resumida y `Retry`; cancelar una descarga activa requiere confirmación inline.
- Completadas pueden compactarse para que no oculten lo urgente.
- Acciones masivas solo aparecen cuando hay selección y deben indicar el alcance.
- Un estado `Reconnecting` debe ser explícito, no simular actividad normal.

### History / Biblioteca local

**Objetivo:** encontrar y verificar archivos ya descargados.

- Filtros de formato, calidad, artista y orden se mantienen cerca del encabezado.
- Grid para exploración visual; lista o inspector para confirmar metadatos.
- El inspector lateral muestra portada, título, artista, álbum, duración, formato, tamaño y ruta.
- Una sola acción primaria por elemento (`Open`, `Reveal`, `Play` o equivalente); acciones destructivas separadas.
- Empty state debe explicar cómo obtener el primer elemento y ofrecer una acción útil.

### Stats

**Objetivo:** mostrar información operativa sin convertirla en un dashboard genérico.

- Priorizar pocas métricas útiles: descargas, éxito/error, volumen y tiempo.
- Usar tablas o números grandes con contexto temporal; evitar gráficas ornamentales.
- Los estados sin datos deben ser honestos y no inventar actividad.

### Settings — Preferencias y audio

**Objetivo:** configurar una vez y reconocer claramente qué cambió.

- Agrupar por `Account`, `Download`, `Audio`, `Storage` y `Interface`.
- Campos con label visible, valor actual y descripción corta.
- El botón `Save` es único y estable; mostrar dirty state y resultado de guardado.
- Errores aparecen junto al campo y en un resumen accesible si hay varios.
- Las preferencias de formato/calidad deben mostrar impacto antes de guardar.

### Preview player

- Barra fija inferior con portada, título/artista, play/pause, seek y duración.
- Waveform como visualización técnica, no como fondo ornamental.
- En móvil se reduce a título, portada y control principal; abrir el resto con una acción accesible.
- El reproductor no debe tapar contenido ni robar el foco al cambiar de vista.

## 7. Componentes y estados

### Botones

- Primario: fondo blanco, texto oscuro, alto contraste; una acción por región.
- Secundario: superficie graphite y borde sutil.
- Ghost: icono o texto de baja prominencia, pero con área táctil completa.
- Danger: reservado a cancelar, borrar o cerrar sesión; nunca usarlo para llamar la atención.
- Todos tienen estados hover, pressed, disabled, focus-visible y loading.

### Inputs, selects y filtros

- Label visible; placeholder no reemplaza al label.
- Focus ring de al menos `2 px`, visible sobre cualquier superficie.
- El valor seleccionado y el estado de error deben anunciarse semánticamente.
- Los filtros activos se pueden quitar individualmente y tienen alternativa de teclado.

### Loading, empty, error y success

- Loading: skeleton tonal con dimensiones estables para evitar saltos de layout.
- Empty: explica el estado, la causa probable y una siguiente acción.
- Error: lenguaje concreto, conserva datos que no se hayan perdido y ofrece retry cuando sea seguro.
- Success: feedback breve y no bloqueante; no interrumpir una descarga con un toast por cada avance.
- Toasts: máximo tres visibles, cierre manual, `role="status"` para informativos y `role="alert"` para errores.

### Filas y selección

- Toda fila interactiva debe tener un target claro, hover/pressed visible y foco completo.
- Separar la acción de seleccionar de la acción de abrir o descargar.
- No usar doble clic como única forma de acción.

## 8. Motion y rendimiento

- Motion comunica causalidad: apertura de panel, cambio de progreso, selección y reproducción.
- Duraciones orientativas: `120–180 ms` para controles y `180–240 ms` para paneles.
- No animar layout completo, blur grande ni elementos constantemente para crear “vida”.
- Respetar `prefers-reduced-motion: reduce`; eliminar transforms y loops no esenciales.
- Reservar dimensiones de portadas e imágenes; usar lazy loading fuera del viewport.
- Debounce para búsquedas y evitar polling duplicado; el WebSocket sigue siendo la fuente de actualizaciones en vivo.

## 9. Accesibilidad y calidad

- Orden de headings lógico: una vista, un `h1`, luego secciones.
- Navegación completa por teclado y `Escape` para cerrar superficies.
- `aria-label` en icon-only buttons; `aria-expanded` y `aria-controls` en toggles de panel.
- Foco gestionado al abrir/cerrar paneles sin dejarlo atrapado en una superficie cerrada.
- Estados de conexión, progreso y error deben exponerse a tecnologías asistivas.
- Alt text describe la portada; si es decorativa, usar `alt=""`.
- Verificar contraste, zoom, reduced motion y viewport móvil antes de publicar.

## 10. Mapa de implementación

| Responsabilidad | Ubicación actual |
|---|---|
| Shell, tabs, conexión y paneles | `frontend/src/App.tsx`, `frontend/src/components/NavBar.tsx` |
| Tokens, primitives y responsive | `frontend/src/index.css` |
| Búsqueda y resultados | `frontend/src/components/SearchView.tsx`, `ArtistView.tsx` |
| Cola y acciones de descarga | `frontend/src/components/QueueView.tsx`, `DownloadActivityPanel.tsx` |
| Historial, biblioteca y métricas | `frontend/src/components/HistoryView.tsx`, `StatsView.tsx` |
| Preferencias | `frontend/src/components/SettingsPanel.tsx` |
| Preview y waveform | `frontend/src/components/AudioPlayerFooter.tsx` |
| Estados de sesión | `frontend/src/components/AuthGate.tsx` |
| Feedback global | `frontend/src/components/ToastContainer.tsx` |

## 11. Criterios de aceptación

- La acción primaria de cada vista se identifica en menos de un segundo.
- El usuario puede cambiar de Search a Queue sin perder contexto ni estado de descarga.
- El progreso no depende de toasts y sigue visible en actividad/cola.
- El shell funciona en escritorio, tablet y móvil sin scroll horizontal accidental.
- Todos los controles principales tienen foco visible, label accesible y target táctil suficiente.
- Los estados loading, vacío, error, retry, reconnecting y success tienen representación explícita.
- El contraste y reduced motion se mantienen al aplicar el tema oscuro.
- `npm test -- --run`, `npm run build` y `git diff --check` pasan antes de publicar.

## 12. Referencias Stitch guardadas

Proyecto: `5324288617561675250` — [abrir en Stitch](https://stitch.withgoogle.com/projects/5324288617561675250?pli=1)

| Pantalla | ID Stitch | Material local |
|---|---|---|
| Design System | `asset-stub-assets_135218d5ced84dceb03885a8b515fca1` | Sistema visual incorporado en este documento |
| Explorador y extractor | `264b9ec10e414e16b9f87e1c8bac4425` | `docs/stitch-reference/screens/264b9ec10e414e16b9f87e1c8bac4425/` |
| Cola y monitoreo | `025db632fb8f4a80bf15db6e172518c2` | `docs/stitch-reference/screens/025db632fb8f4a80bf15db6e172518c2/` |
| Biblioteca local | `848d3a7140934cb09de39f361645e0e8` | `docs/stitch-reference/screens/848d3a7140934cb09de39f361645e0e8/` |
| Preferencias y audio | `03872f07754d42d7994f5ffe6bb88948` | `docs/stitch-reference/screens/03872f07754d42d7994f5ffe6bb88948/` |

Cada carpeta de pantalla contiene `screen.png` y `code.html` exportados desde Stitch para consulta visual y comparación durante futuras iteraciones.
