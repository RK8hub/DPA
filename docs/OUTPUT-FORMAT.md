# Formato de salida

Todo lo que produce el pipeline vive dentro del proyecto, en
`<workspace>/<proyecto>/`. Este documento describe la estructura, el
significado de cada estado y el formato de cada archivo.

## Estructura del proyecto

```
workspace/<proyecto>/
├── project.yaml            datos + config del proyecto (fuente: init/import/skills/TUI)
├── state.yaml              máquina de estados: etapas, fingerprints, runs, decisiones
├── inventory.json          inventario de la exportación (etapa B)
├── analysis.json           análisis del lote (etapa C)
├── rules/
│   ├── design-rules.yaml   reglas con estado y procedencia (etapa D)
│   └── questions.yaml      preguntas de descubrimiento con respuestas (etapa D)
├── specs/
│   ├── index.json          índice de componentes + reglas aprobadas (etapa E)
│   └── components/
│       ├── <Comp>.json     especificación validada contra el esquema
│       └── <Comp>.md       la misma especificación, legible
├── output/
│   └── <perfil>/           react-css/ o astro-css/: código generado + READMEs
├── reports/
│   ├── IMPORT-REPORT.md
│   ├── ANALYSIS.md
│   ├── COMPONENT-MAP.md
│   ├── uncertainties.md
│   ├── DESIGN-RULES.md
│   ├── DECISIONS.md
│   ├── generation-notes.md
│   ├── VALIDATION.md
│   ├── validation-report.json
│   ├── DELIVERY.md
│   └── REVIEW-CHECKLIST.md
├── runs/
│   ├── <run_id>.jsonl      log estructurado por ejecución
│   └── agent-runs/         prompts y resultados de adaptadores (si se usó)
├── logs/
│   └── summary.md          resumen humano de todas las ejecuciones
├── context/
│   └── agent-package/      CONTEXT.md + context.json (etapa/context)
└── .skills/                skills importadas a nivel proyecto (con skill.yaml)
```

`<run_id>` tiene la forma `yyyymmddThhmmssZ-<hex6>`.

## Estados de las etapas

`state.yaml → stages.<id>.status`:

| Estado | Significado | Qué lo cambia |
| --- | --- | --- |
| `pending` | Nunca corrió, o quedó re-puesta | `init` de `state`; `complete()` de una etapa previa baja las `stale` a `pending` |
| `in_progress` | Ejecución en curso (solo existe mientras corre) | `Pipeline.begin()`; un crash puede dejarlo pegado y `resume` lo trata como no `done` |
| `done` | Completada con sus artefactos registrados | `Pipeline.complete()` |
| `failed` | Falló; el motivo está en `notes`, en el `RunRecord.error` y en `runs/*.jsonl` (`stage_failed`) | `Pipeline.fail()` |
| `stale` | Estaba `done` pero sus entradas cambiaron o una etapa previa quedó `stale` | `refresh_staleness()` (lo llaman `status` y `resumable()`) |

`status` muestra además, en `--json`, `just_marked_stale` con los pares
`(etapa, motivo)` detectados en esa consulta (p. ej.
`cambiaron las entradas 'source-tree'`).

También hay estados de **decisiones**: preguntas `open` / `answered` /
`postponed` y reglas `proposed` / `approved` / `rejected`
(`rules/questions.yaml`, `rules/design-rules.yaml`), reflejados en
`state.decisions_pending`.

## Estados de validación (etapa G)

Cada check de `reports/validation-report.json` tiene `status`:

| Estado | Significado |
| --- | --- |
| `PASS` | Ejecutado, sin hallazgos, con evidencia adjunta |
| `FAIL` | Ejecutado, con hallazgo que invalida el resultado; incluye evidencia y ubicación |
| `SKIPPED` | **No se ejecutó**; el `detail` dice por qué (herramienta ausente, falta de aprobación, no aplica) |
| `NEEDS_REVIEW` | Requiere criterio humano (fidelidad, accesibilidad subjetiva, ambigüedad residual) |

> **Regla clave: `SKIPPED` y `NEEDS_REVIEW` no significan que pasó.**
> `SKIPPED` significa que la comprobación **no se ejecutó**; `NEEDS_REVIEW`
> significa que **alguien tiene que mirarlo**. `VALIDATION.md` lo repite en su
> sección "Recordatorio" y el checklist marca esos ítems como pendientes.

Veredicto global (`verdict`):

| Veredicto | Condición |
| --- | --- |
| `fail` | Hay al menos un `FAIL` |
| `pass_with_review` | Sin `FAIL`, pero hay al menos un `NEEDS_REVIEW` |
| `pass` | Ni `FAIL` ni `NEEDS_REVIEW` (los `SKIPPED` no afectan el veredicto, pero se listan siempre) |

`state.last_validation` guarda `created_at`, `profile`, `verdict` y `summary`.
El comando `validate` devuelve exit `1` solo si hay `FAIL`.

Veredicto de la entrega (`report`): toma `verdict` de
`validation-report.json`, o el literal `sin validar` si nunca se validó.

## Procedencia de hallazgos

Todo hallazgo de `analysis.json` (y su espejo en los informes) lleva
`classification`, con estas etiquetas de lectura:

| Etiqueta | Valor en JSON | Significado |
| --- | --- | --- |
| **Observado** | `observed` | Respaldado por el contenido de un archivo, con referencia (archivo, línea cuando hay) |
| **Inferido** | `inferred` | Interpretación con justificación explícita; nunca presentada como hecho |
| **Propuesto** | `proposed` | Cambio o regla sugerida; espera aprobación humana |
| **Pendiente** | `pending` | Pregunta sin resolver que requiere decisión humana |

La misma convención se aplica a los `provenance` de props/variantes dentro de
`specs/components/<Comp>.json` (`observed` / `inferred` / `proposed`) y a la
procedencia de las reglas (`provenance.kind`: `user` para reglas guiadas,
`derived` para reglas que nacen de respuestas).

## Salidas `--json`

Todos los comandos excepto `tui` aceptan `--json` y emiten un único objeto
JSON en stdout (UTF-8, indentado, sin ASCII-escape). Resumen por comando:

| Comando | Contenido del JSON |
| --- | --- |
| `init` | `project`, `path`, `workspace`, `missing_dependencies[]` |
| `doctor` | `ok`, `design_pipeline_version`, `checks[]` (`name`, `ok`, `required`, `detail`, `remedy`) |
| `status` | `project`, `path`, `source`, `current_stage`, `stages[]`, `decisions_pending[]`, `last_validation`, `recent_runs[]`, `just_marked_stale[]` |
| `import` | `project`, `source`, `files`, `duplicates`, `broken_references`, `embedded_stylesheets`, `unanalyzed`, `report` |
| `analyze` | `project`, `components[]` (nombres), `findings`, `uncertainties`, `limitations` |
| `rules init` | `project`, `mode`, `detail` |
| `rules answer` | `project`, `answered[]`, `rules_created[]`, `errors[]` |
| `rules approve` | `project`, `decided[]` (`id`, `status`) |
| `rules show` | `project`, `questions[]`, `rules[]` |
| `spec` | `project`, `created_at`, `analysis_fingerprint`, `approved_rules[]`, `components[]` |
| `generate` | `project`, `profile`, `output`, `files`, `needs_review[]` |
| `validate` | `project` + el reporte completo (`created_at`, `profile`, `verdict`, `summary`, `checks[]`) |
| `report` | `project`, `delivery`, `checklist`, `output`, `needs_review_count`, `verdict` |
| `resume` | `project`, `executed[]` (por etapa: `stage`, `notes` + payload), `pending[]` |
| `context` | `project`, `markdown`, `json` (rutas) |
| `agent list` | `adapters[]` (todos los campos de `AgentAdapter`) |
| `agent run` | `adapter`, `status`, `exit_code`, `duration_seconds`, `prompt_file`, `result_file`, `command[]` |
| `skills list` | `skills[]` (records completos) |
| `skills inspect` | el record completo de la skill |
| `skills validate` | `ok`, `errors[]`, `warnings[]` |
| `skills add` | el record importado |
| `skills enable/disable` | `skill`, `enabled` |
| `skills remove` | `removed` |
| `status`/`resume` sin trabajo | `executed: []`, `pending: []` |

Errores: se imprimen como `Error: <mensaje>` en **stderr** y el exit es `1`
(`2` para uso inválido, p. ej. sin subcomando).

## Formato de cada archivo

### `reports/IMPORT-REPORT.md` (etapa B)

Render de `reporting/import_report.py`: encabezado con fuente, fecha, huella
`sha256` del árbol y cantidad/tamaño de archivos; tabla de **Categorías**
(component, style, data, vector, ...); **Exclusiones aplicadas**; **Duplicados
por contenido** (con `sha256` y tamaño); **Referencias rotas** (tabla archivo /
referencia / motivo); **Referencias externas** (paquetes y URLs, máximo 40
listadas); **Archivos no analizados** (con motivo); y **Notas de seguridad**
(fuente intacta, nada ejecutado).

### `reports/ANALYSIS.md` (etapa C)

Render de `analysis/reports.py → render_analysis`: encabezado (fecha, huella
del inventario, cantidades), recordatorio de las cuatro clasificaciones, luego
secciones **Observado / Inferido / Propuesto / Pendiente** con ítems
`- **[tipo]** mensaje` + `Fuente` y `Justificación`; tabla **Componentes**
(Componente | Archivo | Props | Interactivo | Relaciones); tabla **Tokens
detectados**; **Duplicaciones aparentes** (con % de similitud y la advertencia
de que no implica intercambialidad); **Limitaciones de la exportación**.

### `reports/COMPONENT-MAP.md` (etapa C)

Por componente: ruta, props, interactividad (con hooks), imports de
componentes, estilos, recursos, paquetes y hallazgos de accesibilidad con
número de línea; al final, sección **Relaciones** con el grafo textual
`origen → destino`.

### `reports/uncertainties.md` (etapa C)

Por incertidumbre: `## <id> — <categoría>` con **Pregunta**, **Fuente**,
**Opciones** (si hay) y **Recomendación** (si hay). Son la materia prima del
modo descubrimiento de `rules`.

### `reports/DESIGN-RULES.md` (etapa D)

Render de `rules/manager.py → render_rules_reports` (idempotente): encabezado
con fecha y la advertencia de que `proposed` todavía no se aplican; tres
secciones — **Aprobadas (se aplican en spec/generate)**, **Propuestas
(pendientes de aprobación)** y **Rechazadas** — con ítems
`- **r-001** (categoría): texto de la regla`.

### `reports/DECISIONS.md` (etapa D)

Mismo renderizador: encabezado con la nota "Regenerado desde los datos
máquina; editar directamente no tiene efecto"; sección **Preguntas** con un
`### q-001 (categoría) — estado` por pregunta (Pregunta, Procedencia,
Respuesta con fecha si existe, Opciones, Recomendación) y sección **Reglas**
con `- **r-001** [estado] (categoría) — texto` más la línea de procedencia
(`kind → origin`, y decisión con quién/cuándo si ya se decidió).

### `specs/components/<Comp>.json` y `<Comp>.md` (etapa E)

El JSON es la fuente de verdad, validada contra
`data/schemas/component-spec.schema.json` (si falla, la etapa entera falla).
Claves: `schema_version`, `name`, `source` (`path`, `sha256`), `identity`,
`props[]` (con `provenance`), `states[]`, `variants[]`, `structure[]`
(esqueleto superficial: tag, depth, classes), `tokens_used[]`,
`dependencies` (`local`, `packages`, `assets`), `responsive[]`,
`interactions[]`, `accessibility[]` (ítems `NEEDS_REVIEW`),
`fidelity_constraints[]`, `related[]`, `applied_rules[]` (solo `approved`),
`open_questions[]`, `limitations[]`.

El `.md` (`render_spec_markdown`) es la versión legible de esas mismas claves:
fuente/sha256, propósito, tabla de props con procedencia, variantes, estados,
estructura, clases y tokens, responsive, dependencias, interacciones,
accesibilidad, restricciones de fidelidad, reglas aplicadas, preguntas
abiertas y limitaciones.

`specs/index.json`: `schema_version`, `created_at`, `analysis_fingerprint`,
`approved_rules[]` y `components[]` (name, source, interactive, props, variants,
related).

### `reports/generation-notes.md` (etapa F)

Encabezado (fecha, perfil, cantidad de reglas aprobadas aplicadas y de
reglas todavía `proposed`), **Archivos generados** (`- ruta (created|copied|
transformed) — nota`), **Decisiones y transformaciones** (p. ej. "isla React:
requiere @astrojs/react"), **Revisión humana pendiente**, **Reglas
aprobadas**, **Reglas pendientes de aprobación** y **Limitaciones conocidas**
(sin Tailwind, sin dependencias instaladas, fuente intacta).

### `reports/VALIDATION.md` y `reports/validation-report.json` (etapa G)

El JSON (`ValidationReport.to_dict()`) tiene `created_at`, `profile`,
`verdict`, `summary` (conteos por estado) y `checks[]` con `id`, `name`,
`status`, `detail`, `evidence` (objeto libre: comando, `exit_code`,
conteos...) y `limitations[]`.

El Markdown (`render_validation_markdown`) repite el encabezado (fecha, perfil,
veredicto, resumen) y por cada check una sección
`## <símbolo> <ESTADO> — <nombre>` con **Detalle**, **Evidencia** (JSON
resumido a 400 caracteres) y **Limitación** por cada una; cierra con el
**Recordatorio** de que `SKIPPED` y `NEEDS_REVIEW` no significan que pasó.
(El renderizador real precede cada estado con un símbolo gráfico; este
documento lo transcribe como texto.)

### `reports/DELIVERY.md` (etapa H)

Encabezado con fecha, perfil, **ruta absoluta de salida** y veredicto. Secciones:
**Componentes generados** (lista de archivos relativos), **Reglas aplicadas**,
**Reglas pendientes (no aplicadas)**, **Validaciones ejecutadas** (solo PASS),
**Validaciones omitidas y motivo** (los SKIPPED), **Revisión humana
pendiente (N)**, **Estado del pipeline** (etapa: estado · duración),
**Diferencias relevantes respecto de la fuente** y **Limitaciones
declaradas**. Cierra con la frase de que la entrega está lista para revisión
humana, no para producción directa.

### `reports/REVIEW-CHECKLIST.md` (etapa H)

Render de `reporting/summary.py → _render_checklist`: checklist con casillas.
Secciones: **Revisión visual y de fidelidad** (comparar uno por uno, verificar
tokens, confirmar que no se introdujo nada nuevo, revisar breakpoints),
**Revisión funcional** (probar props/variantes; para `astro-css` se agregan
los ítems de `@astrojs/react` y `client:*`), **Ítems pendientes registrados
por el pipeline** (los `NEEDS_REVIEW` de validación, los de generación, las
reglas `proposed` y las preguntas sin responder), **Validación** (una línea
por check, con la casilla marcada cuando el estado es `SKIPPED`,
`NEEDS_REVIEW` o `FAIL`) y **Entrega** (copiar la salida, correr
build/lint/tests en el proyecto destino, registrar reglas aplicadas).

### `context/agent-package/CONTEXT.md` y `context.json`

`CONTEXT.md`: estado del pipeline (tabla), fuente, decisiones pendientes,
última validación, análisis (componentes, hallazgos por procedencia,
incertidumbres, limitaciones), preguntas y reglas, salida generada, tareas
sugeridas de revisión y **límites** para quien reciba el paquete. `context.json`
es el mismo contenido machine-readable (`schema_version`, `generated_at`,
`stages`, `decisions_pending`, `last_validation`, `analysis`).

### `logs/summary.md`

Bloques `## Ejecución <run_id> — etapa <id> (<fecha>)` con líneas resumen que
agrega cada etapa (conteos, veredictos, rutas) y los intentos bloqueados de
agentes.

### `runs/<run_id>.jsonl`

Una línea JSON por evento: `ts`, `run_id`, `stage`, `type` y campos propios.
Tipos observados: `stage_start`, `skills_activated`, `stage_done`,
`stage_failed`, `command`, `agent_run_requested`, `agent_run_blocked`. Todos
los campos pasan por la redacción de secretos.

### `state.yaml`

`schema_version`, `project`, `created_at`, `updated_at`, `source_path`,
`stages` (por etapa: `id`, `label`, `status`, timestamps, `duration_seconds`,
`artifacts`, `inputs` con fingerprints, `notes`), `runs` (recortado a
`reporting.keep_runs`), `decisions_pending`, `last_validation`. Se escribe de
forma atómica y se rechaza al leer si `schema_version` no es `1`.
