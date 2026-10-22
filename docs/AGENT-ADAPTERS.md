# Adaptadores de agentes

`design-pipeline` no trae ningún adaptador pre-declarado ni afirma
compatibilidad con ninguna CLI de agente. Lo que ofrece es:

1. una **interfaz común** para declarar adaptadores en la configuración;
2. **detección informativa** (presencia en `PATH`, sin ejecutar nada);
3. un **paquete de contexto exportable** que funciona sin agente;
4. una **ejecución acotada** tras doble permiso, con salida redactada y log.

El núcleo del pipeline funciona **sin agente**: todas las etapas, informes y
la validación son locales y deterministas.

> **Honestidad obligatoria:** el mecanismo de ejecución (`agent run`) se probó
> **solo con un stub local** (un comando tipo `cat {prompt_file}` declarado en
> la configuración de un proyecto de prueba), **no con ninguna CLI de agente
> real**. Ningún adaptador de agentes reales viene pre-declarado. El estado
> `detected-not-run` significa "el ejecutable está en `PATH` y todavía no se
> ejecutó": **no** implica compatibilidad probada.

## Interfaz común (`adapters/base.py`)

```python
@dataclass
class AgentAdapter:
    id: str
    label: str
    command: list[str]           # plantilla con {prompt_file} y {project}
    detection: str               # ejecutable a buscar en PATH ("" = solo config)
    prompt_method: str           # "prompt-file" | "stdin"
    skills_support: str          # "instructions-in-prompt" | "none"
    interactive: str             # "yes" | "no" | "unknown"
    capabilities: list[str]
    limitations: list[str]
    result_capture: str          # default: "stdout+stderr (redactado) a runs/agent-runs/"
    source: str                  # "config" | "builtin"
    status: str                  # declared-not-tested | detected-not-run | tested-with-stub
    executable_path: str
```

Significado de cada campo:

- **`command`**: plantilla de argv (lista de strings). Se sustituyen los
  placeholders conocidos y se ejecuta tal cual (sin shell).
- **`detection`**: qué ejecutable buscar con `shutil.which` para la detección
  informativa. Cadena vacía = adaptador solo declarado en config.
- **`prompt_method`**: cómo recibe el contexto. `prompt-file` (la ruta del
  prompt reemplaza a `{prompt_file}` en el comando) o `stdin` (además se envía
  el texto por la entrada estándar; el archivo igual se guarda como auditoría).
- **`skills_support`**: qué declara el adaptador sobre skills:
  `instructions-in-prompt` (las instrucciones habilitadas viajan como texto en
  el prompt) o `none`. Es declarativo: el pipeline no verifica el soporte real.
- **`interactive`**: si la CLI espera terminal interactiva
  (`yes`/`no`/`unknown`).
- **`capabilities` / `limitations`**: listas libres que el autor del adaptador
  declara; se muestran en `agent list --json` y no las valida el pipeline.
- **`result_capture`**: texto informativo sobre dónde queda la salida.
- **`status`**: `declared-not-tested` (declarado, no probado),
  `detected-not-run` (el ejecutable está en `PATH`, no se ejecutó),
  `tested-with-stub` (solo el estado del stub con el que se probó el
  mecanismo; no se aplica automáticamente a nada).

## Declaración en la configuración (`agent.adapters`)

Los adaptadores se declaran en cualquier archivo de configuración que fusione
`load_config()` (recomendado: `project.yaml` del proyecto, o el config de
usuario). Clave raíz `agent.adapters`, mapeo `{id: especificación}`:

```yaml
agent:
  allow_execution: false   # la ejecución sigue deshabilitada hasta que la actives
  adapters:
    mi-agente:
      label: "Mi agente (declaración de ejemplo, no probada)"
      command: ["mi-agente", "--prompt-file", "{prompt_file}", "--project", "{project}"]
      detection: "mi-agente"
      prompt_method: prompt-file        # default
      skills_support: instructions-in-prompt   # default
      interactive: "no"
      capabilities: ["edición de archivos", "lectura del workspace"]
      limitations: ["requiere login previo", "no probado con este pipeline"]
```

Reglas que valida `adapters/registry.py` al cargar:

- `command` debe ser una **lista de strings no vacía** (si no, error).
- Los placeholders permitidos son exactamente **`{prompt_file}`**,
  **`{project}`** y **`{workspace}`**; cualquier otra llave `...` en el comando
  produce un error que lista los permitidos.
- `prompt_method` debe ser `prompt-file` o `stdin`.
- `detection` default: el primer elemento de `command`.

## Detección informativa

- `design-pipeline doctor` incluye el chequeo `agentes-detectados`, que solo
  informa si hay en `PATH` alguna de `opencode`, `claude`, `codex`, `gemini`,
  `aider`, con el remate explícito: "La detección no implica compatibilidad;
  verificá el adaptador correspondiente". Es un chequeo **no requerido**.
- `design-pipeline agent list [-p <proyecto>]` muestra los adaptadores
  declarados con su detección, estado (`declared-not-tested` /
  `detected-not-run`), método de prompt y, si se resolvió, la ruta del
  ejecutable. Con `--json` devuelve el array `adapters` completo.

Si no hay adaptadores declarados, `agent list` lo dice y remite a
`docs/AGENT-ADAPTERS.md`.

Nota: `agent list` **sin** `--project` usa la configuración global (donde casi
nunca hay adaptadores); con `--project` fusiona también ese `project.yaml`.

## Paquete de contexto (`design-pipeline context`)

Es el mecanismo principal y **no ejecuta nada**:

```bash
design-pipeline context -p <proyecto>
```

Escribe dos archivos en `context/agent-package/`:

- **`CONTEXT.md`**: Markdown legible con estado del pipeline (tabla etapa /
  estado / artefactos), fuente importada, decisiones pendientes, última
  validación, resumen del análisis (hallazgos por procedencia), preguntas y
  reglas, salida generada, tareas sugeridas de revisión y **límites** para
  quien reciba el paquete (no modificar la exportación, no ejecutar scripts,
  no presentar nada como aprobado, marcar Pendiente en lugar de inventar).
- **`context.json`**: el mismo contenido en formato máquina
  (`schema_version`, `generated_at`, `stages`, `decisions_pending`,
  `last_validation`, `analysis`).

El paquete solo incluye datos del workspace (ya sujetos a la redacción
existente) y no contiene secretos ni credenciales. Sirve para cargarlo a mano
en cualquier herramienta o revisor humano. La TUI tiene el mismo flujo en
"Exportar contexto para un agente".

## Ejecución acotada (`design-pipeline agent run`)

```bash
design-pipeline agent run <id-adaptador> -p <proyecto> \
  [--extra-instructions "texto"] [--allow-execution] [--json]
```

**Doble permiso (ambos obligatorios, en este orden):**

1. configuración efectiva con `agent.allow_execution: true`; y
2. el flag `--allow-execution` en la línea de comandos.

Sin el primero: `La ejecución de agentes está deshabilitada: activá
'agent.allow_execution: true' en la configuración.`
Sin el segundo: `Falta el permiso explícito: repetí el comando con
--allow-execution.` Ambos fallan con exit `1`; el log registra primero
`agent_run_requested` y después `agent_run_blocked` con el motivo.

Cuando ambos permisos están, el flujo es:

1. Se regenera el paquete de contexto y se usa su `CONTEXT.md` como prompt
   (con `--extra-instructions` se concatena un bloque
   "Instrucciones adicionales del usuario").
2. Se registra el evento `agent_run_requested` en `runs/<run_id>.jsonl` con el
   flag, el permiso de config y el prefijo `sha256` del prompt (no el texto).
3. El prompt se escribe en `runs/agent-runs/<fecha>-<id>.prompt.md` (queda
   como auditoría).
4. Se construye el comando sustituyendo `{prompt_file}`, `{project}` y
   `{workspace}`; se verifica que el ejecutable exista en `PATH`.
5. Se ejecuta con `subprocess.run` **sin shell**, con un entorno mínimo
   (`PATH`, `HOME`, `LANG=C.UTF-8`), capturando stdout/stderr y con timeout de
   **300 segundos**.
6. La salida pasa por la redacción de secretos (`utils.redact` sobre
   stdout/stderr y `utils.redact_text` sobre el texto del comando) y se guarda
   en `runs/agent-runs/<fecha>-<id>.result.md` (stdout truncado a 20 000
   caracteres, stderr a 5 000), con fecha, comando redactado, código de salida,
   duración y hash del prompt.
7. Se registra el evento `command` en el log y un bloque en `logs/summary.md`;
   el estado del adaptador en la respuesta es `ok` (exit 0), `error` (exit
   distinto) o `timeout`.

La TUI **no** tiene ninguna opción de ejecutar agentes; la ejecución existe
solo en la CLI.

## Ejemplo completo de adaptador propio (stub con el que se probó)

En `project.yaml` de un proyecto de prueba se declaró:

```yaml
agent:
  allow_execution: true
  adapters:
    stub-cat:
      label: "Stub local (cat)"
      command: ["cat", "{prompt_file}"]
      detection: "cat"
      prompt_method: prompt-file
```

Y se verificó:

```bash
design-pipeline agent list -p demo
# ID        DETECCIÓN  ESTADO             MÉTODO PROMPT
# stub-cat  cat        detected-not-run   prompt-file

design-pipeline agent run stub-cat -p demo
# Error: Falta el permiso explícito: repetí el comando con --allow-execution.

design-pipeline agent run stub-cat -p demo --allow-execution
# Adaptador: stub-cat → ok (exit 0)
# Resultado: .../runs/agent-runs/20261022T195938Z-stub-cat.result.md
# Prompt:    .../runs/agent-runs/20261022T195938Z-stub-cat.prompt.md
```

Ese stub es **todo lo que se probó** de la ejecución: valida el doble
permiso, la sustitución de placeholders, la captura con redacción y el log. No
dice nada sobre cómo se comporta una CLI de agente real.

## Cómo incorporar otra CLI

**Lo que no requiere código** (solo configuración): cualquier CLI que pueda
recibir el prompt por archivo o por stdin y que no necesite interacción:

```yaml
agent:
  adapters:
    mi-cli:
      command: ["mi-cli", "run", "--input-file", "{prompt_file}"]
      detection: "mi-cli"
      prompt_method: prompt-file
```

**Lo que sí requeriría modificar el paquete** (hoy no está soportado):

- un método de prompt nuevo (p. ej. pasar contexto por variable de entorno o
  por archivo intermedio con formato propio): habría que agregar el valor a
  `KNOWN_METHODS` y su lógica de armado de entrada en
  `adapters/registry.py` (`run_adapter`);
- placeholders nuevos (ya existen `{prompt_file}`, `{project}` y
  `{workspace}`; uno distinto requiere agregarlo a `KNOWN_PLACEHOLDERS` y a
  `build_command`);
- estrategias de captura distintas (p. ej. leer un archivo de resultado que
  deja la CLI en disco en vez de stdout): hoy la captura es siempre
  stdout/stderr redactados, y habría que extender `run_adapter` y el dataclass
  `AgentAdapter`;
- detección de compatibilidad real (un smoke test que ejecute la CLI con un
  prompt mínimo y registre `tested-with-stub`): **no existe**; el estado
  `detected-not-run` nunca avanza solo.

Cualquier cambio de este tipo debe mantener los invariantes de
`docs/SECURITY.md`: doble permiso, sin shell, entorno mínimo, timeout,
redacción y registro en `runs/*.jsonl`.

## Limitaciones

- Sin adaptadores pre-declarados: `agent list` arranca vacío en todo proyecto
  nuevo.
- Sin compatibilidad probada con ninguna CLI de agente real; el único caso
  probado es un stub local (`cat`).
- `skills_support`, `capabilities`, `limitations` e `interactive` son
  declaraciones del autor del adaptador: el pipeline los muestra, no los
  verifica.
- La detección (`doctor` y `agent list`) solo prueba presencia en `PATH`.
- La ejecución corre con los permisos del usuario que invoca la CLI y sin
  sandbox de procesos (ver `docs/SECURITY.md`).
- No hay streaming ni modo interactivo: la corrida es un subprocess con timeout
  de 300 s y la salida se guarda en archivos.
