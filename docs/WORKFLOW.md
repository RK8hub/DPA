# Flujo de trabajo: las 8 etapas

El pipeline tiene ocho etapas identificadas por letra (`engine/stages.py`).
Cada `StageDef` declara `id`, `letter`, `label`, `requires` (requisitos
previos) y `expected_artifacts`. El orden es fijo y el motor rechaza saltos:
`Pipeline.begin()` lanza `StageOrderError` si un requisito no está en estado
`done`.

| Letra | `id` | Etapa | Requiere (`requires`) |
| --- | --- | --- | --- |
| A | `init` | Inicialización | — |
| B | `import` | Importación e inventario | `init` |
| C | `analyze` | Análisis del lote | `import` |
| D | `rules` | Reglas de diseño y preguntas | `import` |
| E | `spec` | Especificación intermedia | `analyze` |
| F | `generate` | Generación | `spec` |
| G | `validate` | Validación | `generate` |
| H | `report` | Revisión y entrega | `validate` |

Observación importante: `rules` solo requiere `import` a nivel de motor, pero
el modo descubrimiento exige además `analysis.json` (falla con "El modo
descubrimiento requiere la etapa analyze previa").

Estados posibles por etapa: `pending`, `in_progress`, `done`, `failed`,
`stale`.

---

## A — `init` (Inicialización)

- **Entrada:** nombre del proyecto (kebab-case) y workspace
  (`--workspace`, `DESIGN_PIPELINE_WORKSPACE` o `./workspace`).
- **Acciones:** crea el esquema de carpetas (`ensure_layout`), escribe
  `project.yaml` (con `generation.profile` tomado de
  `generation.default_profile`), siembra las 5 skills internas en
  `skills.enabled` (`seed_internal_skills`), corre `doctor` y registra la
  etapa.
- **Salidas:** `project.yaml`, `state.yaml`.
- **Puertas de aprobación:** ninguna. Las ausencias de `doctor` se listan como
  informativas y no bloquean (salvo que falte algo requerido: Python o PyYAML).
- **Reanudación:** queda `done` de una vez; solo vuelve a `failed`/`stale` si
  alguien borra el estado. `init` no está en la lista de `resumable()` salvo
  que su `state.yaml` no exista.

## B — `import` (Importación e inventario)

- **Entrada:** carpeta de la exportación (argumento posicional de
  `design-pipeline import <carpeta>`; en `resume` se pasa con `--source`; en la
  TUI se pide por prompt).
- **Acciones:** recorre el árbol con `utils.iter_files` (no sigue symlinks,
  aplica `exclusions`, registra archivos sobre `max_file_size_mb` como no
  analizados), clasifica por categoría, calcula `sha256` por archivo y la huella
  del árbol (`source_fingerprint`), detecta duplicados exactos, referencias
  locales rotas, referencias externas (paquetes/URLs) y archivos no
  analizados. **Nunca escribe dentro de la fuente ni ejecuta nada.**
- **Salidas:** `inventory.json`, `reports/IMPORT-REPORT.md`; registra
  `source.path` en `project.yaml` y `source_path` en `state.yaml`.
- **Puertas de aprobación:** ninguna (es lectura y registro).
- **Reanudación:** requiere `init` `done`. Su entrada fingerprint es el árbol
  de la fuente (`@source-tree`): si la exportación cambia, la etapa queda
  `stale` y `resume` la reejecuta.

## C — `analyze` (Análisis del lote)

- **Entrada:** `inventory.json` + la fuente en disco.
- **Acciones:** `analysis.analyzer.analyze_batch` detecta componentes
  (JSX/TSX), props, estados, variantes, relaciones, hojas de estilo, tokens
  (custom properties), accesibilidad (heurísticas `alt`/teclado), duplicaciones
  aparentes, assets sin referenciar, incertidumbres y limitaciones. Cada
  hallazgo queda clasificado: `observed` (Observado), `inferred` (Inferido),
  `proposed` (Propuesto), `pending` (Pendiente).
- **Salidas:** `analysis.json`, `reports/ANALYSIS.md`,
  `reports/COMPONENT-MAP.md`, `reports/uncertainties.md`.
- **Puertas de aprobación:** ninguna. Lo Propuesto acá no se aplica solo:
  necesita volverse regla y ser aprobado en la etapa D.
- **Reanudación:** requiere `import` `done`; entra en `stale` si cambia
  `inventory.json`.

## D — `rules` (Reglas de diseño y preguntas)

Dos modos (`rules init`):

- **Descubrimiento** (`--mode discovery`, default): requiere `analysis.json`.
  Genera preguntas concretas con opciones y recomendación (perfil de destino,
  enfoque de estilos, tokens, interactividad, accesibilidad, duplicaciones y
  las derivadas de `reports/uncertainties.md`). Idempotente: no duplica
  preguntas existentes.
- **Guiado** (`--mode guided`): **requiere `--rules-file`** con YAML (clave
  `rules:`) o Markdown (viñetas `- regla`). Cada regla entra como `proposed`,
  salvo que se pase `--approve`, que aprueba **las reglas importadas en esa
  corrida** (las ya existentes no se re-aprueban).

Complementos:

- `rules answer --id <q> --value <valor>` (o `--answers-file` con mapping YAML
  `{id: valor}`, o `--postpone`): la respuesta debe ser una de las opciones
  válidas. Después se derivan reglas **propuestas** automáticamente
  (`derive_rules_from_answers`), nunca aprobadas.
- `rules approve --id <r-001> [--id ...] | --all [--reject]`: única forma de
  pasar una regla a `approved` (o `rejected`).
- `rules` / `rules show`: estado de preguntas (`open`/`answered`/`postponed`) y
  reglas (`proposed`/`approved`/`rejected`).

- **Entradas:** `inventory.json` y `analysis.json` (fingerprints de la etapa);
  en modo guiado, el archivo del usuario.
- **Salidas:** `rules/design-rules.yaml`, `rules/questions.yaml`,
  `reports/DESIGN-RULES.md`, `reports/DECISIONS.md`. Sincroniza
  `state.decisions_pending` con las preguntas `open` y las reglas `proposed`.
- **Puertas de aprobación (reales):**
  - `rules init --mode guided` exige `--rules-file`;
  - **las reglas solo se aplican en `spec`/`generate` después de
    `rules approve`** (una regla `proposed` aparece en el checklist como "no
    aplicada");
  - las respuestas y aprobaciones son el único camino para que algo quede
    registrado como decisión humana.
- **Derivación de reglas:** toda pregunta respondida deriva una regla
  `proposed` con procedencia `answer:<id>`: `q-001` (perfil), `q-002`
  (estilos) y la de `tokens` usan textos concretos (plantilla por id o por
  categoría, con la opción `unificar` incluida); el resto registra la decisión
  con un texto genérico. Ninguna se aplica sin `rules approve`.
- **Cada decisión se pregunta una sola vez:** si el hallazgo `adhoc` y la
  incertidumbre del análisis cubren el mismo tema (p. ej. tokens y
  accesibilidad), se emite **una** pregunta —la de descubrimiento, con valores
  simples y rationale— y la procedencia anota la incertidumbre que cubre
  (`discovery+u-00X`).
- **Reanudación:** requiere `import` `done` a nivel de motor; el modo
  descubrimiento falla con mensaje accionable si `analyze` no corrió (y
  `resume` la hará correr antes si está pendiente). Las preguntas `open` no
  bloquean el pipeline: `resume` continúa igual; en la TUI, el flujo completo
  avisa antes de seguir con preguntas sin responder y pide confirmación
  (default "no").

## E — `spec` (Especificación intermedia)

- **Entradas:** `analysis.json`, reglas `approved`, preguntas `open`/`postponed`
  (quedan como `open_questions` en cada spec) y los `sha256` del inventario.
- **Acciones:** construye un `ComponentSpec` por componente (identidad, props
  con procedencia, estados, variantes, estructura superficial, tokens usados,
  dependencias, responsive, interacciones, accesibilidad, restricciones de
  fidelidad, reglas aplicadas, preguntas abiertas, limitaciones) y lo valida
  contra `data/schemas/component-spec.schema.json` **antes** de escribirlo: si
  alguna spec no cumple el esquema, la etapa falla entera.
- **Salidas:** `specs/index.json` (con `approved_rules` y el índice de
  componentes), `specs/components/<Comp>.json` y `specs/components/<Comp>.md`.
- **Puertas de aprobación:** ninguna propia, pero aplica **solo** las reglas
  `approved`; las `proposed` se ignoran y quedan listadas en
  `reports/generation-notes.md` y en `DELIVERY.md`.
- **Reanudación:** requiere `analyze` `done`; entra en `stale` si cambia
  `analysis.json` o los archivos de reglas.

## F — `generate` (Generación)

- **Entradas:** specs, análisis, reglas aprobadas, la fuente (solo lectura) y
  el perfil: `--profile {react-css,astro-css}` o `generation.profile` del
  proyecto (default `react-css`).
- **Acciones:** `Profile.generate()` escribe en `output/<perfil>/` preservando
  la estructura de la fuente. `react-css` copia literalmente y agrega READMEs
  por componente, un `index.ts` y un README de perfil; `astro-css` convierte
  estáticos a `.astro` y deja los interactivos como isla React (TSX copiado +
  wrapper `.astro` con `client:load`). Registra cada archivo como
  `created`/`copied`/`transformed` y toda ambigüedad como `needs_review`.
- **Salidas:** `output/<perfil>/` (árbol completo), `reports/generation-notes.md`.
- **Puertas de aprobación (reales):**
  - **en la TUI**, el flujo "Ejecutar pipeline hasta la entrega" pide
    confirmación explícita antes de generar (`Aprobás generar el código de
    salida ahora? (se escribirá en output/)`, default **no**) y de nuevo antes
    de continuar con `validate`/`report`; el flujo "Ejecutar la etapa siguiente"
    pide una confirmación genérica (default sí) para cualquier etapa;
  - **en la CLI, `generate` no pide confirmación**: se ejecuta y escribe en
    `output/<perfil>/` (el workspace es del proyecto, la fuente no se toca);
  - no instala dependencias de ninguna manera.
- **Reanudación:** requiere `spec` `done`; entra en `stale` si cambia el árbol
  `specs/` o las reglas.

## G — `validate` (Validación)

- **Entradas:** `output/<perfil>/`, specs, manifiestos del workspace y la
  huella de la fuente registrada en `inventory.json`.
- **Acciones:** 11 checks deterministas (`validators/runner.py`), todos con
  detalle, evidencia y limitaciones: `integrity`, `isolation`,
  `spec-schema`, `manifests`, `references`, `class-coverage`, `accessibility`,
  `framework-integration`, `external-build`, `responsive`, `visual`.
- **Salidas:** `reports/validation-report.json`, `reports/VALIDATION.md` y
  `state.last_validation`.
- **Estados por check:** `PASS`, `FAIL`, `SKIPPED`, `NEEDS_REVIEW`. Regla
  estricta: **nunca se escribe `PASS` sin ejecución registrada**.
- **Veredicto:** `fail` si hay algún `FAIL`; `pass_with_review` si hay algún
  `NEEDS_REVIEW`; `pass` solo si no hay ninguno de los dos (`SKIPPED` no
  afecta el veredicto, pero se reporta siempre).
- **Puerta de aprobación (real) — comandos externos:** el check `external-build`
  solo puede correr si se cumplen **todas** estas condiciones:
  1. existe `package.json` dentro de `output/<perfil>/` (los perfiles actuales
     generan archivos sueltos, así que normalmente se saltea con ese motivo);
  2. el flag `--approve-external` en la línea de comandos;
  3. `validation.approve_external_commands: true` en la configuración efectiva;
  4. `npm` disponible en el `PATH`.

  Si falta cualquiera, el estado es `SKIPPED` con el motivo escrito. En
  `resume` se pasa con `--approve-external`; en la TUI, la pregunta
  `¿Permitir comandos externos (build/lint) en validate?` (default **no**)
  solo aporta el flag: la configuración también debe autorizarlo.
- **Códigos de salida:** `1` si hay algún `FAIL`; `0` con `pass` o
  `pass_with_review`.
- **Reanudación:** requiere `generate` `done`; entra en `stale` si cambia el
  árbol de salida. Los checks `responsive` y `visual` son **siempre**
  `SKIPPED` en esta versión (no hay ejecutor de navegador ni herramienta de
  captura): eso está documentado como limitación, no como aprobación.

## H — `report` (Revisión y entrega)

- **Entradas:** `output/<perfil>/`, `reports/validation-report.json`,
  `reports/generation-notes.md`, reglas y `state.decisions_pending`.
- **Acciones:** recolecta todos los ítems de revisión pendientes (checks
  `NEEDS_REVIEW`, sección "Revisión humana pendiente" de las notas de
  generación, reglas `proposed` y preguntas `q-*` sin responder) y renderiza
  dos informes.
- **Salidas:** `reports/DELIVERY.md` (ruta absoluta de salida, veredicto,
  archivos, reglas aplicadas y pendientes, validaciones ejecutadas y
  omitidas con motivo, limitaciones declaradas) y
  `reports/REVIEW-CHECKLIST.md` (checklist de revisión humana).
- **Puertas de aprobación:** la entrega **nunca** declara "listo para
  producción": el cierre lo hace una persona completando el checklist. Ese
  paso es manual, fuera del pipeline.
- **Reanudación:** requiere `validate` `done`; entra en `stale` si cambia
  `reports/validation-report.json`.

---

## Reanudación (`resume`, `status` y TUI)

- `status` llama a `refresh_staleness()` antes de mostrar y reporta
  `just_marked_stale` con los motivos.
- `resume` recorre `resumable()` (etapas en `pending`, `stale` o `failed`, en
  orden A→H), recalcula después de cada etapa y se detiene ante la primera
  falla. Opciones:
  - `--until <etapa>`: hasta esa etapa inclusive (p. ej. `--until spec`);
  - `--source <carpeta>`: ruta de la exportación si hay que reimportar sin
    registro previo;
  - `--profile <perfil>` para `generate`/`validate`/`report`;
  - `--approve-external` para el check de build de `validate`.
  Si no hay nada pendiente imprime "nada pendiente" y devuelve `0`.
- La TUI usa los mismos runners (`engine/runner.py`): "Ejecutar la etapa
  siguiente" corre la primera pendiente con confirmación; "Ejecutar pipeline
  hasta la entrega" avisa de preguntas abiertas, pide confirmación para
  `generate` y para continuar después de generar, y pregunta por comandos
  externos en `validate`.

## Puertas de aprobación — resumen

| Puerta | Mecanismo | Dónde |
| --- | --- | --- |
| Reglas aprobadas | `rules approve --id ...` / `--all` (o `--approve` al importar reglas guiadas nuevas) | CLI y TUI |
| Comandos externos en `validate` | flag `--approve-external` **y** config `validation.approve_external_commands` | CLI, `resume`, TUI (la TUI solo aporta el flag) |
| Generar código en la TUI | confirmación explícita, default no | TUI |
| Continuar con preguntas abiertas en la TUI | confirmación, default no | TUI |
| Skills `executive` | importar/habilitar exige config `skills.allow_executive` | CLI y TUI |
| Eliminar una skill | `skills remove` exige `--yes` | CLI |
| Ejecutar un agente | config `agent.allow_execution` **y** flag `--allow-execution` | CLI (`agent run`) — no existe en la TUI |
| Respuestas a preguntas | `rules answer` (o TUI); nunca se responden solas | CLI y TUI |
