# Configuración

La configuración se arma fusionando varias fuentes en un único dict
(`design_pipeline.config.load_config`) y se consulta con claves anidadas
(`utils.dotted_get`).

## Jerarquía de fusión

Orden de precedencia, de menor a mayor:

1. **Defaults empaquetados** — `src/design_pipeline/data/config/defaults.yaml`
   (leídos con `importlib.resources`, siempre presentes).
2. **Config de usuario** — `~/.config/design-pipeline/config.yaml`
   - la ruta se resuelve con `user_config_path()`:
   - si existe la variable `DESIGN_PIPELINE_CONFIG`, se usa esa ruta;
   - si no, `$XDG_CONFIG_HOME/design-pipeline/config.yaml` o
     `~/.config/design-pipeline/config.yaml`;
   - si el archivo no existe, se ignora silenciosamente (siguen los defaults);
     si existe pero no es un mapping YAML o es ilegible, falla con `ConfigError`.
3. **Config del proyecto** — `<workspace>/<proyecto>/project.yaml`
   (solo cuando `load_config` recibe `project_dir`; es lo que hace
   `load_project` al abrir un proyecto).
4. **Variable de entorno `DESIGN_PIPELINE_WORKSPACE`**
   (sobrescribe `workspace_root`).
5. **Flags de la línea de comandos** (`overrides`): máxima prioridad.

La fusión es `utils.deep_merge`: los sub-diccionarios se combinan
recursivamente y los escalares del overlay pisan a los del base. Es decir, se
puede activar `agent.allow_execution` en el proyecto sin perder el resto de la
config de usuario.

Detalle del workspace: `workspace_root(config, cli_workspace)` usa
`--workspace` si está presente; si no, `config["workspace_root"]`; si no,
`./workspace`. Por lo tanto el orden efectivo para el workspace es:
flag `--workspace` > `DESIGN_PIPELINE_WORKSPACE` > `project.yaml` >
config de usuario > default `./workspace`.

Ejemplo verificado:

```bash
DESIGN_PIPELINE_WORKSPACE=/tmp/mi-ws design-pipeline init demo   # crea en /tmp/mi-ws/demo
design-pipeline init demo --workspace /otro-ws                   # gana el flag
```

## Archivo de configuración por defecto

`src/design_pipeline/data/config/defaults.yaml`, clave por clave:

```yaml
schema_version: 1
```

Versión del esquema de la configuración. Se conserva en el dict fusionado;
`state.yaml` y `project.yaml` tienen su propio `schema_version: 1` aparte.

```yaml
workspace_root: ./workspace
```

Raíz donde viven los proyectos (`<workspace_root>/<proyecto>/`). Relativa al
directorio de trabajo. Se puede sobrescribir con `--workspace` o con la
variable de entorno `DESIGN_PIPELINE_WORKSPACE`.

```yaml
exclusions:
  - ".git"
  - "node_modules"
  - "dist"
  - "build"
  - ".next"
  - ".nuxt"
  - ".cache"
  - ".turbo"
  - "coverage"
  - "__pycache__"
  - ".DS_Store"
  - "*.lock"
  - "*.min.js"
  - "*.min.css"
  - ".env"
  - ".env.*"
  - "*.pem"
  - "id_rsa*"
  - "credentials*"
  - "secrets*"
```

Patrones de nombre/glob (comparados con `fnmatch`) que se excluyen al
inventariar la exportación y al calcular fingerprints de árboles. La lista
incluye artefactos de build, cachés y **archivos con pinta de secretos**
(`.env*`, `*.pem`, `id_rsa*`, `credentials*`, `secrets*`): no entran ni al
inventario ni a los hashes.

```yaml
max_file_size_mb: 5
```

Archivos más grandes que este tamaño se **registran pero no se analizan**
(aparecen en `inventory.json` y en `IMPORT-REPORT.md` como "no analizados",
con el motivo). Aplica a la lectura de texto de la exportación; no limita la
importación de skills (esas tienen sus propios límites de 2 MB / 20 MB, ver
`docs/SKILLS.md`).

```yaml
text_extensions:
  - ".jsx"
  - ".tsx"
  - ".js"
  - ".ts"
  - ".mjs"
  - ".cjs"
  - ".css"
  - ".scss"
  - ".json"
  - ".svg"
  - ".md"
  - ".html"
  - ".txt"
  - ".yml"
  - ".yaml"
```

Extensiones que se tratan como texto: sobre ellas se buscan imports,
`require()`, `url()`, `src`/`href` y clases CSS. Cualquier otro archivo se
inventarioa por tamaño y hash, sin análisis de referencias.

```yaml
agent:
  allow_execution: false
  adapters: {}
```

- `agent.allow_execution`: primer permiso del doble gate para ejecutar una CLI
  externa con `agent run` (el segundo es el flag `--allow-execution`).
  `false` por defecto: sin esta clave en `true`, `agent run` falla siempre.
- `agent.adapters`: mapeo `{id: especificación}` de adaptadores. Vacío por
  defecto: **no hay ningún adaptador pre-declarado**. Formato completo en
  `docs/AGENT-ADAPTERS.md`.

```yaml
skills:
  global_dir: null
  allow_executive: false
```

- `skills.global_dir`: directorio de skills globales. `null` significa
  `~/.config/design-pipeline/skills` (la carpeta del config de usuario +
  `/skills`). Se puede apuntar a cualquier ruta con `~`.
- `skills.allow_executive`: segundo permiso del doble gate para skills con
  `mode: executive`: sin esta clave en `true`, ni `skills add` ni
  `skills enable` aceptan una skill executive. Aun activada, la skill **nunca
  ejecuta scripts sola**.

```yaml
generation:
  default_profile: react-css
```

Perfil que `init` guarda en `generation.profile` del `project.yaml` y que
usan `generate`, `validate` y `report` cuando no se pasa `--profile`.
Perfiles disponibles: `react-css`, `astro-css` (`generators/registry.py`).

```yaml
validation:
  viewports: [375, 768, 1280]
  approve_external_commands: false
```

- `validation.viewports`: breakpoints que el check `responsive` reporta como
  "configurados". **Informativo en esta versión**: no hay ejecutor de
  navegador, el check es siempre `SKIPPED` y los valores solo aparecen como
  evidencia.
- `validation.approve_external_commands`: segundo permiso del doble gate para
  correr comandos externos en `validate` (el primero es el flag
  `--approve-external`). Además el output debe contener `package.json` y debe
  haber `npm`; si no, el check queda `SKIPPED` con el motivo.

```yaml
reporting:
  keep_runs: 20
```

Cuántos `RunRecord` conservar en `state.yaml` (lista `runs`). Al superarlo se
recorta desde el inicio: los registros viejos se descartan del estado (los
archivos `runs/<run_id>.jsonl` no se borran desde acá).

## Configuración por proyecto (`project.yaml`)

`<workspace>/<proyecto>/project.yaml` cumple doble función: es el archivo de
**datos** del proyecto **y** su nivel de configuración (paso 3 de la
jerarquía). Al cargar un proyecto, `load_project` llama a
`load_config(project_dir=...)`, así que cualquier clave de
`defaults.yaml` escrita acá pisa a las capas anteriores solo para ese proyecto.

Contenido que escribe el propio pipeline (no lo edites a mano si querés que
los comandos mantengan coherencia):

```yaml
schema_version: 1
name: demo
created_at: "..."
updated_at: "..."
source:
  path: /ruta/a/la/exportacion      # la registra `import`
skills:
  enabled:                          # la gestionan init / skills enable|disable
    - analyze-batch
    - inspect-design
generation:
  profile: react-css                # la fija init, rules answer q-001 o la TUI
```

Y puede agregar claves de configuración para este proyecto, por ejemplo:

```yaml
agent:
  allow_execution: true
  adapters:
    stub-cat:
      command: ["cat", "{prompt_file}"]
      detection: "cat"
validation:
  approve_external_commands: true
skills:
  allow_executive: true
```

Cuidado con una trampa: la clave `skills.enabled` (lista de skills
habilitadas) convive con las claves de configuración `skills.global_dir` y
`skills.allow_executive` en la misma raíz `skills`. Como `deep_merge` combina
sub-diccionarios, ambas conviven sin pisarse; pero si escribís `skills:` a
mano, acordate de que estás editando también el bloque de datos.

También se puede editar la configuración de un proyecto agregando las claves
al mismo `project.yaml` (no hay un archivo separado de config por proyecto).

## Consulta de claves

En el código, las claves anidadas se leen con:

```python
from design_pipeline.utils import dotted_get

dotted_get(config, "agent.allow_execution")          # default None
dotted_get(config, "reporting.keep_runs", 20)        # default explícito
```

Si algún tramo falta o no es dict, devuelve el default (nunca lanza). Los
comandos que necesitan una clave usan siempre el valor fusionado de
`load_config`/`project.config`, nunca leen YAML por su cuenta.

## Variables de entorno

| Variable | Efecto |
| --- | --- |
| `DESIGN_PIPELINE_WORKSPACE` | Fija `workspace_root` (por encima del `project.yaml`, por debajo de `--workspace`) |
| `DESIGN_PIPELINE_CONFIG` | Cambia la ruta del config de usuario |
| `XDG_CONFIG_HOME` | Base para el config de usuario y las skills globales si no hay `DESIGN_PIPELINE_CONFIG` |

No se leen otras variables de entorno para la configuración, y la CLI no
registra variables de entorno en sus logs (ver `docs/SECURITY.md`).

## Verificación rápida

```bash
design-pipeline doctor --json | grep -A3 config-usuario
# muestra la ruta resuelta del config de usuario y si existe

design-pipeline status -p <proyecto> --json | head
# estado efectivo del proyecto tras fusionar todas las capas
```

`doctor` también muestra la ruta de `skills-globales` efectiva.

## Limitaciones

- No hay comando `config show`: para inspeccionar el resultado fusionado hay
  que leer los archivos (defaults, config de usuario, `project.yaml`) o
  mirarlo en el código.
- No hay validación de esquema del config de usuario: una clave desconocida se
  fusiona sin error y simplemente no la usa nadie (un typo silencioso).
- Los overrides por flag son mínimos (`--workspace`, `--profile`,
  `--approve-external`, `--allow-execution`): no todas las claves se pueden
  pisar desde la línea de comandos.
