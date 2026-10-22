# Arquitectura

Este documento describe la estructura real del paquete
`src/design_pipeline/`, las responsabilidades de cada módulo y cómo circulan
los datos. Los nombres de módulos y funciones citados existen en el código.

## Principios de diseño

- **La CLI es una capa delgada** (`cli.py`): resuelve proyecto y configuración,
  llama al motor y formatea la salida. Toda la lógica de negocio vive en
  módulos del paquete, de modo que CLI, `resume` y TUI comparten el mismo
  motor y los mismos runners.
- **Sin IA propia ni APIs externas.** El análisis es determinista (patrones
  regulares sobre los archivos) y la única dependencia de runtime es PyYAML.
- **Todo artefacto humano (Markdown) se regenera desde datos máquina (JSON/YAML).**
  Editar un informe a mano no tiene efecto: la fuente de verdad es
  `inventory.json`, `analysis.json`, `rules/*.yaml`, `specs/*.json` y
  `reports/validation-report.json`.
- **Nada se ejecuta sin permiso explícito** (comandos externos, agentes,
  skills), y toda ejecución queda registrada en `runs/*.jsonl`.

## Mapa del paquete

```
src/design_pipeline/
├── cli.py              parser argparse (build_parser) y comandos
├── tui/
│   ├── app.py          menús; delega siempre en el motor
│   └── console.py      primitivas de consola (inyectables en tests)
├── engine/
│   ├── stages.py       StageDef, STAGES (A–H), estados, downstream()
│   ├── state.py        ProjectState/StageState/RunRecord → state.yaml
│   ├── pipeline.py     ciclo begin/complete/fail, fingerprints, staleness
│   ├── runner.py       runners por etapa compartidos (CLI/resume/TUI)
│   └── log.py          RunLogger: runs/<run_id>.jsonl + logs/summary.md
├── workspace/
│   ├── paths.py        ProjectPaths (todas las rutas) y ensure_layout()
│   └── project.py      Project, create_project/load_project/list_projects
├── importers/
│   ├── inventory.py    inventario seguro (hashs, refs, duplicados)
│   └── stage.py        run_import → inventory.json + IMPORT-REPORT.md
├── analysis/
│   ├── analyzer.py     analyze_batch, hallazgos clasificados, tokens
│   ├── reports.py      render de ANALYSIS.md / COMPONENT-MAP.md / uncertainties.md
│   └── stage.py        run_analyze / load_analysis
├── rules/
│   └── manager.py      preguntas, reglas, respuestas, aprobaciones, informes
├── spec/
│   └── builder.py      ComponentSpec, build_specs, validación por esquema
├── generators/
│   ├── base.py         Profile (ABC), GenerationContext, GenerationResult
│   ├── registry.py     PROFILES: react-css, astro-css
│   ├── react_profile.py  copia literal + READMEs + barrel index.ts
│   ├── astro_profile.py  estáticos → .astro; interactivos → isla React
│   ├── astro_converter.py convertor conservador JSX/TSX → Astro
│   └── stage.py        run_generate + reports/generation-notes.md
├── validators/
│   ├── schema.py       validador de JSON Schema (subconjunto, sin dependencias)
│   └── runner.py       11 checks, veredicto, VALIDATION.md + report JSON
├── reporting/
│   ├── import_report.py  render de IMPORT-REPORT.md
│   └── summary.py        DELIVERY.md y REVIEW-CHECKLIST.md (etapa H)
├── skills/
│   └── registry.py     descubrimiento, validación, importación, habilitación
├── adapters/
│   ├── base.py         AgentAdapter (interfaz común)
│   ├── registry.py     agent.adapters, detección, ejecución acotada
│   └── context.py      paquete de contexto CONTEXT.md + context.json
├── doctor.py           run_doctor (chequeos del entorno)
├── config.py           load_config, workspace_root, rutas de config
├── utils.py            tiempo, hashes, escritura atómica, redacción, merges
├── errors.py           excepciones de dominio (todas heredan DesignPipelineError)
├── templates.py        render de README por componente y por perfil
└── data/
    ├── config/defaults.yaml     defaults de configuración
    ├── principles/*.md          fidelity, safety, traceability, human-review
    ├── skills/<nombre>/SKILL.md las 5 skills internas
    └── schemas/component-spec.schema.json  esquema de las especificaciones
```

## Motor de estados (`engine/`)

### Definición de etapas (`stages.py`)

`StageDef` es un dataclass congelado: `id`, `letter` (A–H), `label`,
`requires` (tupla de etapas previas), `description` y `expected_artifacts`.
La tupla `STAGES` fija el orden; `STAGE_BY_ID` y `STAGE_IDS` indexan por id.
Estados posibles: `pending`, `in_progress`, `done`, `failed`, `stale`.

### Estado persistido (`state.py`)

`ProjectState` se serializa a `state.yaml` (escritura atómica vía
`utils.atomic_write_text`). Guarda `schema_version` (actualmente `1`, se rechaza
cualquier versión distinta al cargar), `source_path`, un `StageState` por etapa
(`status`, timestamps, `duration_seconds`, `artifacts`, `inputs` con los
fingerprints, `notes`), la lista `runs` (recortada a `reporting.keep_runs`),
`decisions_pending` y `last_validation`.

### Ciclo de vida (`pipeline.py`)

`Pipeline` administra el ciclo sin conocer la lógica de negocio de cada etapa:

- `begin(stage_id)`:
  1. verifica `missing_requirements()` y lanza `StageOrderError` si falta alguna
     etapa previa;
  2. genera `run_id` (`yyyymmddThhmmssZ-<hex>`), abre un `RunLogger` en
     `runs/<run_id>.jsonl`;
  3. calcula los fingerprints de entrada (`compute_inputs`) y marca la etapa
     `in_progress`;
  4. registra el evento `stage_start` y, si hay skills habilitadas que declaran
     esa etapa, el evento `skills_activated` (solo trazabilidad: las skills
     nunca se ejecutan);
  5. agrega un `RunRecord` a `state.runs` y persiste.
- `complete(handle, artifacts, notes, summary_lines)`: marca `done`, recalcula
  los fingerprints al finalizar (la ruta de la fuente, por ejemplo, solo se
  conoce cuando la etapa corre), pasa las etapas aguas abajo de `stale` a
  `pending`, emite `stage_done`, cierra el run y agrega un bloque en
  `logs/summary.md`.
- `fail(handle, error)`: marca `failed`, emite `stage_failed` y copia el error
  al `RunRecord`.

### Fingerprints y obsolescencia

Cada etapa registra la huella de sus entradas en `_FINGERPRINT_SOURCES`:

| Etapa | Entradas hasheadas |
| --- | --- |
| `import` | `@source-tree` (árbol completo de la exportación) |
| `analyze` | `inventory.json` |
| `rules` | `inventory.json`, `analysis.json` |
| `spec` | `analysis.json`, `rules/design-rules.yaml` y `rules/questions.yaml` (opcionales) |
| `generate` | `specs/` (árbol), reglas opcionales |
| `validate` | `output/` (árbol del perfil) |
| `report` | `reports/validation-report.json` |

Los archivos se hashean con `sha256_file`; los directorios con
`tree_fingerprint` (rutas relativas + hashes de contenido, respetando
`exclusions` y sin seguir symlinks). Un archivo opcional ausente se registra
como `""`.

`refresh_staleness()` recorre `STAGES` en orden y marca `stale` toda etapa
`done` cuyos fingerprints cambiaron, cuyo artefacto desapareció o cuya etapa
previa está `stale`/incompleta; devuelve `[(etapa, motivo), ...]`, agrega el
motivo a `notes` y persiste. `resumable()` combina eso con la selección de
etapas en `pending`, `stale` o `failed`, en orden de etapa.

Verificado: si la exportación original cambia después de importarse, `status`
muestra `just_marked_stale` con motivos como
`cambiaron las entradas 'source-tree'` y propaga el `stale` a `analyze`.

### Runners compartidos (`runner.py`)

`RUNNERS` mapea cada etapa a una función
`(project, pipeline, options) -> StageOutcome`, donde `options` es un
diccionario (`source`, `profile`, `approve_external`). `run_stage()` envuelve
al runner con el mismo ciclo `begin`/`complete`/`fail` que la CLI.
`resume_pipeline()` recalcula `resumable()` después de cada etapa (para
respetar el staleness), respeta el límite `--until` (etapa inclusive) y se
detiene ante la primera falla, dejando lo ejecutado registrado. Lo usan
`design-pipeline resume` y los menús de la TUI.

### Logs (`log.py`)

`RunLogger` escribe una línea JSON por evento (`ts`, `run_id`, `stage`, `type`
más los campos propios) en `runs/<run_id>.jsonl`, pasando **todos** los campos
por `utils.redact`. `append_summary()` agrega bloques legibles a
`logs/summary.md`. Nunca registra variables de entorno completas.

## Configuración fusionada (`config.py`)

`load_config(project_dir=None, overrides=None)` combina, en orden:

1. `packaged_defaults()` → `data/config/defaults.yaml` (recursos del paquete);
2. config de usuario → `~/.config/design-pipeline/config.yaml` (respeta
   `DESIGN_PIPELINE_CONFIG` y `XDG_CONFIG_HOME`);
3. `project_dir/project.yaml` si se pasa el directorio del proyecto;
4. variable de entorno `DESIGN_PIPELINE_WORKSPACE` (sobrescribe
   `workspace_root`);
5. `overrides` (flags CLI), que tienen máxima prioridad.

La fusión es `utils.deep_merge` (los dicts se combinan recursivamente y los
escalares del overlay ganan). El acceso a claves anidadas se hace con
`utils.dotted_get(config, "agent.allow_execution", default)`, que devuelve el
default si algún tramo no existe.

`workspace_root(config, cli_workspace)` resuelve la raíz: el flag
`--workspace` gana sobre `config["workspace_root"]` (default `./workspace`).
Detalle completo en `docs/CONFIGURATION.md`.

## Proyectos (`workspace/`)

- `paths.ProjectPaths` centraliza todas las rutas del proyecto dentro del
  workspace (`project.yaml`, `state.yaml`, `inventory.json`, `analysis.json`,
  `reports/`, `rules/`, `specs/`, `output/`, `context/agent-package/`, `runs/`,
  `logs/`, `.skills/`) y `ensure_layout()` crea el esquema de carpetas.
- `project.Project` junta `name`, `paths`, `config` (fusionada) y `data` (el
  contenido de `project.yaml`: `source.path`, `skills.enabled`,
  `generation.profile`). `create_project()` valida el slug
  (`minúsculas, dígitos y guiones`, 2–64) y crea los datos base; la siembra
  de las skills internas la hace `cmd_init` (y el flujo equivalente de la TUI)
  con `seed_internal_skills`. `load_project()` carga datos y estado;
  `list_projects()` enumera los directorios con `project.yaml`.

## Flujo de datos

```
exportación (solo lectura)
   │  importers/inventory.py
   ▼
inventory.json ──► reports/IMPORT-REPORT.md
   │  analysis/analyzer.py
   ▼
analysis.json ──► reports/ANALYSIS.md, COMPONENT-MAP.md, uncertainties.md
   │  rules/manager.py (preguntas → respuestas → reglas propuestas → approve)
   ▼
rules/design-rules.yaml + rules/questions.yaml
   ──► reports/DESIGN-RULES.md, reports/DECISIONS.md
   │  spec/builder.py (valida contra component-spec.schema.json)
   ▼
specs/index.json + specs/components/<Comp>.json|.md
   │  generators/registry.py → Profile.generate()
   ▼
output/<perfil>/ ──► reports/generation-notes.md
   │  validators/runner.py (11 checks)
   ▼
reports/validation-report.json + reports/VALIDATION.md
   │  reporting/summary.py
   ▼
reports/DELIVERY.md + reports/REVIEW-CHECKLIST.md

transversal: state.yaml (etapas + fingerprints) · runs/*.jsonl · logs/summary.md
```

## Extensiones previstas

- **Perfil de salida nuevo**: subclasear `generators.base.Profile` y
  registrarlo en `generators/registry.PROFILES` (hoy `react-css` y
  `astro-css`). El núcleo no conoce perfiles concretos.
- **Adaptador de agente**: se declara en la configuración
  (`agent.adapters`) sin tocar código; ver `docs/AGENT-ADAPTERS.md` para lo
  que sí requeriría cambios de código (métodos de prompt o placeholders nuevos).
- **Skill externa**: carpeta con `SKILL.md`, sin código del paquete; ver
  `docs/SKILLS.md`.

## Limitaciones de arquitectura

- `validators/schema.py` implementa un subconjunto de JSON Schema (`type`,
  `enum`, `required`, `properties`, `items`, `additionalProperties`,
  `minItems`, `pattern`, `$ref` local). Los esquemas publicados siguen siendo
  JSON Schema estándar, pero consumirlos con otra librería podría aceptar más
  de lo que este validador valida.
- No hay sandbox de procesos: la ejecución externa se limita por permisos,
  redacción y timeouts.
- La detección de CLIs de agente en `doctor` es informativa y no establece
  compatibilidad.
