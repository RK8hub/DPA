# design-pipeline

CLI local de terminal que orquesta un pipeline de 8 etapas para preparar
contexto, registrar decisiones y generar componentes de UI revisables a partir
de exportaciones de diseño (carpetas con JSX/TSX, CSS, assets).

No tiene IA propia ni consume APIs externas: todo el trabajo es determinista
(inventario, análisis por patrones, especificación, generación por perfil y
validación con evidencia). Las decisiones que requieren criterio humano quedan
registradas como preguntas, reglas `proposed` o ítems `NEEDS_REVIEW`, nunca se
resuelven solas.

> **¿Te llegó este repositorio como agente de IA?** Andá directo a
> [`AGENTS.md`](AGENTS.md): es tu manual de trabajo. Cubre la instalación, la
> notificación obligatoria al usuario al terminarla, el flujo completo paso a
> paso (pedir la exportación, traer las preguntas, generar, validar, entregar)
> y las reglas duras de honestidad y seguridad. En ese flujo, el humano sólo
> responde preguntas y da el visto bueno final.

## Cómo funciona

Ocho etapas con requisitos estrictos y estado persistido en `state.yaml`:

| Letra | Etapa | Comando | Requiere |
| --- | --- | --- | --- |
| A | Inicialización | `init` | — |
| B | Importación e inventario | `import` | `init` |
| C | Análisis del lote | `analyze` | `import` |
| D | Reglas de diseño y preguntas | `rules` | `import` |
| E | Especificación intermedia | `spec` | `analyze` |
| F | Generación | `generate` | `spec` |
| G | Validación | `validate` | `generate` |
| H | Revisión y entrega | `report` | `validate` |

El detalle de entradas, salidas y puertas de aprobación está en
`docs/WORKFLOW.md`.

## Requisitos

- Python 3.11 o superior (verificado con 3.11–3.14; `doctor` falla si es menor).
- PyYAML >= 6.0 (única dependencia de runtime, se instala sola).
- Opcionales: `node`/`npm` (para el check de build externo, que además requiere
  aprobación explícita), `git`, `pytest` para la suite de pruebas.

No se necesita conexión a internet para ninguna función local.

## Instalación

Desde la raíz del repositorio:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Esto instala el paquete en modo editable con la única dependencia (`PyYAML`) y
`pytest` como extra de desarrollo, y crea el ejecutable
`.venv/bin/design-pipeline`.

Verificación:

```bash
.venv/bin/design-pipeline --version
# design-pipeline 0.1.0

.venv/bin/design-pipeline doctor
```

`doctor` imprime `[  OK ]`, `[FALTA]` o `[ERROR]` por cada chequeo (python,
PyYAML, pytest, node, npm, git, CLIs de agente detectadas, config de usuario,
skills globales y workspace). Devuelve `0` si todos los chequeos requeridos
pasan; los no requeridos solo informan.

También podés correr la suite:

```bash
.venv/bin/python -m pytest
```

## Primeros pasos

Todos los comandos siguientes fueron ejecutados y verificados contra la fixture
del repositorio.

```bash
# 1) Crear un proyecto (etapa A). El nombre es kebab-case.
.venv/bin/design-pipeline init demo

# 2) Inventariar la exportación (etapa B). Nunca modifica la fuente.
.venv/bin/design-pipeline import tests/fixtures/fixture-export --project demo

# 3) Analizar el lote (etapa C).
.venv/bin/design-pipeline analyze --project demo

# 4) Generar preguntas de descubrimiento (etapa D).
.venv/bin/design-pipeline rules init --mode discovery --project demo
.venv/bin/design-pipeline rules show --project demo

# 5) Responder preguntas y aprobar las reglas derivadas.
.venv/bin/design-pipeline rules answer --project demo --id q-001 --value react-css
.venv/bin/design-pipeline rules answer --project demo --id q-002 --value css-puro
.venv/bin/design-pipeline rules approve --project demo --all

# 6) Especificación y generación (etapas E y F).
.venv/bin/design-pipeline spec --project demo
.venv/bin/design-pipeline generate --project demo

# 7) Validación y entrega (etapas G y H).
.venv/bin/design-pipeline validate --project demo
.venv/bin/design-pipeline report --project demo

# 8) Estado y reanudación.
.venv/bin/design-pipeline status --project demo
.venv/bin/design-pipeline resume --project demo
```

Salida esperada de `status` con la fixture: las 8 etapas en `done` y el aviso
"Pipeline completo" (las preguntas sin responder siguen listadas como
decisiones pendientes).

Todos los comandos de proyecto aceptan `--project/-p` y `--workspace/-w`; casi
todos aceptan `--json` (ver tabla). Si el workspace vive en otro lado:

```bash
.venv/bin/design-pipeline init demo --workspace /ruta/al/workspace
# o con variable de entorno:
DESIGN_PIPELINE_WORKSPACE=/ruta/al/workspace .venv/bin/design-pipeline init demo
```

## Comandos

Todos los comandos aceptan `-h/--help` con el detalle de sus flags. El parser
global acepta `--version`.

| Comando | Qué hace | `--project/-p` | `--workspace/-w` | `--json` | Flags adicionales |
| --- | --- | --- | --- | --- | --- |
| `init <nombre>` | Crea el proyecto y las skills internas (etapa A) | no (el nombre es posicional) | sí | sí | — |
| `doctor` | Diagnostica dependencias y herramientas | no | sí | sí | — |
| `status` | Estado de las etapas y reanudación | sí | sí | sí | — |
| `import <carpeta>` | Inventario de la exportación, solo lectura (etapa B) | sí | sí | sí | — |
| `analyze` | Componentes, tokens, accesibilidad, incertidumbres (etapa C) | sí | sí | sí | — |
| `rules` | Sin acción: muestra preguntas y reglas | sí | sí | sí | — |
| `rules init` | Crea reglas guiadas o preguntas de descubrimiento | sí | sí | sí | `--mode {discovery,guided}`, `--rules-file`, `--approve` |
| `rules answer` | Registra respuestas | sí | sí | sí | `--id`, `--value`, `--answers-file`, `--postpone` |
| `rules approve` | Aprueba o rechaza reglas propuestas | sí | sí | sí | `--id` (repetible), `--all`, `--reject` |
| `rules show` | Lista preguntas y reglas con su estado | sí | sí | sí | — |
| `spec` | Especificación intermedia por componente (etapa E) | sí | sí | sí | — |
| `generate` | Código de salida por perfil (etapa F) | sí | sí | sí | `--profile {react-css,astro-css}` |
| `validate` | PASS/FAIL/SKIPPED/NEEDS_REVIEW con evidencia (etapa G) | sí | sí | sí | `--profile`, `--approve-external` |
| `report` | DELIVERY.md y REVIEW-CHECKLIST.md (etapa H) | sí | sí | sí | `--profile` |
| `resume` | Ejecuta etapas pendientes/obsoletas/fallidas en orden | sí | sí | sí | `--until`, `--source`, `--profile`, `--approve-external` |
| `tui` | Asistente interactivo en terminal | no | sí | **no** | — |
| `context` | Exporta `context/agent-package/` (CONTEXT.md + context.json) | sí | sí | sí | — |
| `agent` | Sin acción: lista adaptadores declarados | sí | sí | sí | — |
| `agent list` | Lista adaptadores y su detección | sí | sí | sí | — |
| `agent run` | Ejecuta un adaptador con doble permiso | sí | sí | sí | `--extra-instructions`, `--allow-execution` |
| `skills` | Sin acción: lista skills | sí | sí | sí | — |
| `skills list` | Lista skills (interna/global/proyecto) | sí | sí | sí | — |
| `skills inspect <nombre>` | Metadatos, hashes, scripts declarados, preview | sí | sí | sí | — |
| `skills validate <nombre\|ruta>` | Valida una skill registrada o una carpeta | sí | sí | sí | — |
| `skills add <ruta>` | Importa una skill (solo copia + hashes) | sí | sí | sí | — |
| `skills enable <nombre>` | Habilita la skill para el proyecto | sí | sí | sí | — |
| `skills disable <nombre>` | Deshabilita la skill para el proyecto | sí | sí | sí | — |
| `skills remove <nombre>` | Elimina una skill externa (destructivo) | sí | sí | sí | `--yes` (obligatorio) |

Notas de comportamiento verificadas:

- `rules`, `skills` y `agent` sin subacción funcionan como `show`, `list` y
  `list` respectivamente.
- Comandos sin `--project` donde es obligatorio fallan con
  `Error: Este comando requiere --project NOMBRE.` (exit `1`).
- Códigos de salida: `0` ok, `1` error de ejecución, `2` uso inválido (sin
  comando se imprime la ayuda), `130` interrupción (Ctrl-C).
- `validate` devuelve `1` si algún chequeo quedó en `FAIL`; con
  `pass_with_review` o `pass` devuelve `0`.
- `tui` requiere terminal interactiva: sin tty devuelve `1` y sugiere usar la
  CLI o `design-pipeline context`.

## Ejemplo completo con la fixture

`tests/fixtures/fixture-export/` es una exportación pequeña (4 componentes
TSX, 4 CSS, tokens, assets SVG, un JSON y un README) que usan también las
pruebas. Recorrido completo en un workspace aparte:

```bash
WS=/tmp/dp-demo
.venv/bin/design-pipeline init demo -w "$WS"
.venv/bin/design-pipeline import tests/fixtures/fixture-export -p demo -w "$WS"
.venv/bin/design-pipeline analyze -p demo -w "$WS"
.venv/bin/design-pipeline rules init --mode discovery -p demo -w "$WS"
.venv/bin/design-pipeline rules answer -p demo -w "$WS" --id q-001 --value react-css
.venv/bin/design-pipeline rules answer -p demo -w "$WS" --id q-002 --value css-puro
.venv/bin/design-pipeline rules approve -p demo -w "$WS" --all
.venv/bin/design-pipeline spec -p demo -w "$WS"
.venv/bin/design-pipeline generate -p demo -w "$WS"
.venv/bin/design-pipeline validate -p demo -w "$WS"
.venv/bin/design-pipeline report -p demo -w "$WS"
```

Resultados reales de esa corrida:

- `import`: 12 archivos, 0 duplicados, 1 referencia rota (`./old-styles.css` en
  `Legacy.tsx`), 0 no analizados.
- `analyze`: 4 componentes, 4 hojas de estilo, 13 hallazgos, 3 incertidumbres,
  2 limitaciones.
- `rules init --mode discovery`: 8 preguntas (destino, estilos, tokens,
  interactividad, accesibilidad, variantes y las derivadas del análisis).
- `generate`: 14 archivos en `output/react-css/` con 1 ítem de revisión.
- `validate`: veredicto `pass_with_review` (PASS 4, FAIL 0, SKIPPED 4,
  NEEDS_REVIEW 3).
- `report`: 9 ítems de revisión humana en `reports/REVIEW-CHECKLIST.md`.

Salida machine-readable para scripting: agregá `--json` a cualquiera de esos
comandos (por ejemplo `status -p demo -w "$WS" --json`).

## Limitaciones

Estas limitaciones son reales y están declaradas también en los informes:

- **Sin IA propia ni APIs externas.** El pipeline no interpreta intención de
  diseño: analiza archivos con patrones deterministas.
- **No convierte a Tailwind.** Los perfiles generan CSS puro; la conversión a
  utilidades queda como trabajo manual o asistido y se documenta como pendiente.
- **CSS embebido: separado cuando se puede confirmar, `NEEDS_REVIEW` cuando
  no.** Si una exportación trae el CSS pegado al final de un componente tras
  un marcador `/* nombre.css */`, el pipeline lo detecta, lo analiza como hoja
  de estilo y `generate` lo separa a un archivo `.css` real (el JSX/TSX de
  salida queda compilable y el import resuelve). Pero si el bloque no se puede
  confirmar como CSS puro (llaves desbalanceadas, código JS mezclado), **no**
  se transforma: queda como limitación del análisis y `NEEDS_REVIEW` en las
  notas de generación para revisión humana. Nunca se copia sintaxis inválida
  en silencio.
- **Pruebas responsive y comparación visual: siempre `SKIPPED`.** No hay
  ejecutor de navegador implementado ni instalado. Su ausencia **no** garantiza
  que la salida sea responsive ni fiel visualmente.
- **Build/lint externo casi siempre `SKIPPED`.** Los perfiles generan archivos
  sueltos (sin `package.json`), así que el check `external-build` se saltea con
  ese motivo; además exige `--approve-external` **y**
  `validation.approve_external_commands: true` en la configuración, más `npm`
  disponible.
- **No instala dependencias.** React, `@astrojs/react`, etc. deben agregarse a
  mano en el proyecto destino; la salida lo declara en sus README y notas.
- **Adaptadores de agentes: sin adaptadores pre-declarados y sin compatibilidad
  probada con CLIs reales.** El mecanismo de ejecución (`agent run`) se probó
  únicamente con un stub local (`cat {prompt_file}`), nunca con una CLI de
  agente real. La detección de CLIs en `doctor`/`agent list` es informativa:
  `detected-not-run` no implica compatibilidad probada. El núcleo funciona sin
  agente: `design-pipeline context` exporta el paquete para cargarlo a mano.
  Detalle en `docs/AGENT-ADAPTERS.md`.
- **Skills externas nunca se ejecutan.** Se importan como archivos y hashes;
  los scripts declarados solo se muestran para inspección.
- **Reglas derivadas siguen propuestas.** Toda pregunta respondida (modo
  descubrimiento o derivada del análisis) genera automáticamente una regla
  `proposed` con procedencia `answer:<id>`: con texto concreto para destino
  (`q-001`), estilos (`q-002`) y tokens (por categoría), y con registro
  genérico de la decisión para el resto. Nada se aplica sin `rules approve`
  del usuario; para decisiones que no nacen de una pregunta sigue existiendo
  el modo guiado (`rules init --mode guided --rules-file ...`).
- **No hay sandbox de procesos.** La ejecución externa se limita por permisos
  explícitos, redacción y timeouts, no por aislamiento del sistema operativo
  (ver `docs/SECURITY.md`).

## Solución de problemas

| Síntoma | Causa y solución |
| --- | --- |
| `Error: Este comando requiere --project NOMBRE.` | Agregá `-p <proyecto>` (o `--project`). |
| `La etapa 'X' requiere que estén completas: ...` | Ejecutá las etapas previas o `design-pipeline resume -p <proyecto>`. |
| `No existe el proyecto 'x' en ...` | Primero `design-pipeline init <nombre>`. |
| `doctor` marca `ERROR` en `python` o `pyyaml` | Python < 3.11 o PyYAML ausente: recreá el venv con `pip install -e '.[dev]'`. |
| `El modo descubrimiento requiere la etapa analyze previa.` | Corré `analyze` antes de `rules init --mode discovery`. |
| `El modo guiado requiere --rules-file ...` | Pasá `--rules-file` con un YAML (`rules:`) o un Markdown con viñetas. |
| `La ejecución de agentes está deshabilitada...` | Doble permiso: `agent.allow_execution: true` en la config **y** `--allow-execution`. |
| `Falta el permiso explícito: repetí el comando con --allow-execution.` | Igual que arriba: falta el flag. |
| `'x' es executive: activá skills.allow_executive...` | La skill declara `mode: executive`; activá `skills.allow_executive: true` para importarla/habilitarla. |
| `Eliminar una skill es destructivo...` | Repetí con `--yes`. |
| `resume` se detiene o quedan etapas pendientes | Revisá `rules show`: preguntas `open` y reglas `proposed` suelen ser la causa; también puede haber fallado una etapa (mirá `status` y `runs/*.jsonl`). |
| `La TUI necesita una terminal interactiva.` | Usá la CLI o exportá contexto con `design-pipeline context`. |
| `state.yaml ... Versión de esquema ... no soportada` | El `schema_version` del estado no corresponde a esta versión del paquete (versión actual: `1`). |
| Muchos `SKIPPED` en `validate` | Esperado sin `package.json`/npm y siempre en responsive/visual; leé el motivo de cada uno en `reports/VALIDATION.md`. |
| Un aviso de la CLI sugiere un flag que argparse rechaza | Los "Siguientes pasos" impresos por la CLI son solo indicativos; consultá esta tabla o `--help` del subcomando. |

Los artefactos de cada corrida quedan en `runs/*.jsonl` (evento `stage_failed`
cuando algo falla) y el resumen humano en `logs/summary.md`.

## Documentación

- `AGENTS.md` — instrucciones para agentes de IA: instalación, notificación,
  flujo completo y reglas duras (entrypoint para quien conduzca el pipeline).
- `docs/ARCHITECTURE.md` — módulos, responsabilidades y flujo de datos.
- `docs/WORKFLOW.md` — las 8 etapas, puertas de aprobación y reanudación.
- `docs/SKILLS.md` — formato, importación, validación y permisos de skills.
- `docs/AGENT-ADAPTERS.md` — adaptadores de agentes, contexto y ejecución acotada.
- `docs/CONFIGURATION.md` — jerarquía de configuración y claves reales.
- `docs/SECURITY.md` — límites de confianza, ejecución externa y secretos.
- `docs/OUTPUT-FORMAT.md` — estructura de salida y significado de estados.
- `docs/templates/` — plantillas de referencia de los informes generados.

## Licencia

MIT (ver `LICENSE`).
