# Skills

Las skills son carpetas de instrucciones en Markdown con metadatos que el
pipeline **lee, registra y asocia a etapas**, pero nunca ejecuta. Se tratan
como contenido no confiable: toda importación es copia de bytes + hashes, sin
bit de ejecución, sin symlinks y con límites de tamaño.

La implementación vive en `src/design_pipeline/skills/registry.py`.

## Formato

Una skill es una **carpeta** que contiene como mínimo `SKILL.md` con
frontmatter YAML:

```markdown
---
name: mi-skill
description: "Qué hace esta skill y para qué etapa sirve."
version: 0.1.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, write-reports]
tools: []
stages: [analyze]
scripts: []
---

# Cuerpo de la skill

Instrucciones en Markdown...
```

Campos del frontmatter (tal como los lee `validate_skill_dir`):

| Campo | Obligatorio | Regla |
| --- | --- | --- |
| `name` | no (usa el nombre de la carpeta si falta) | kebab-case: `^[a-z0-9][a-z0-9-]{1,63}$`; si se valida como registro, debe coincidir con el nombre esperado |
| `description` | **sí** | vacío produce error |
| `version` | no | libre; se muestra en `skills list` |
| `format` | no | default `markdown-folder` |
| `mode` | no | `instructive` (default) o `executive`; otro valor es error |
| `permissions` | no | lista; los valores fuera de `KNOWN_PERMISSIONS` generan un aviso y se ignoran decorativamente |
| `tools` | no | lista libre, se reporta tal cual |
| `stages` | no | ids de etapa válidos (`init`, `import`, `analyze`, `rules`, `spec`, `generate`, `validate`, `report`); otro valor es error |
| `scripts` | no | rutas relativas dentro de la carpeta; absolutas o con `..` son error, inexistentes son error, existentes generan el aviso "NO se ejecutará automáticamente" |

Permisos que el registro reconoce (`KNOWN_PERMISSIONS`):
`read-workspace`, `read-output`, `write-reports`, `write-rules`,
`write-specs`, `write-output`. Una lista abierta: cualquier otro valor solo se
reporta.

Además, al importar se escribe un `skill.yaml` junto al `SKILL.md` con la
procedencia (ver abajo).

## Descubrimiento (orígenes)

`discover_skills(project, config)` enumera tres orígenes, en este orden:

| Origen (`origin`) | Ubicación |
| --- | --- |
| `internal` | `src/design_pipeline/data/skills/` (embebidas en el paquete) |
| `global` | `skills.global_dir` si está definido; si no, `~/.config/design-pipeline/skills` |
| `project` | `<proyecto>/.skills/` |

El campo `enabled` **no** viene del disco de la skill: es la lista
`skills.enabled` de `project.yaml` (habilitación por proyecto). Sin
`--project`, `skills list` no muestra la habilitación.

Comandos:

```bash
design-pipeline skills list -p <proyecto>        # tabla: nombre, origen, modo, etapas, hab, versión
design-pipeline skills inspect <nombre> -p <proyecto>
design-pipeline skills validate <nombre-o-ruta>  # sin -p funciona para rutas
```

`inspect` muestra metadatos, hash del árbol (`digest`), scripts declarados, la
ruta y un preview de los primeros 400 caracteres del cuerpo.

## Importación (`skills add`)

```bash
design-pipeline skills add /ruta/a/mi-skill -p <proyecto>   # al proyecto (.skills/)
design-pipeline skills add /ruta/a/mi-skill                 # global (~/.config/.../skills)
```

Lo que hace `add_skill` (verificado):

1. Valida la carpeta origen (`validate_skill_dir`); si tiene errores, no sigue.
2. Si la skill es `mode: executive` y `skills.allow_executive` no está en
   `true`, falla **antes** de copiar nada.
3. El destino nunca se sobrescribe: si ya existe una skill con ese nombre,
   falla y sugiere eliminar la existente.
4. Copia con `_safe_copy_tree`, que **rechaza**: archivos u ocultos (cualquier
   componente de ruta que empiece con `.`), symlinks, tipos que no sean
   archivo/carpeta, archivos de más de **2 MB** (`MAX_FILE_BYTES`) y carpetas
   de más de **20 MB** en total (`MAX_TOTAL_BYTES`). La copia es byte a byte
   con `write_bytes`, es decir **sin heredar el bit de ejecución** del origen.
   Ante cualquier rechazo, borra lo que esta importación creó y falla.
5. Escribe `skill.yaml` con procedencia y hashes:

   ```yaml
   name: mi-skill
   version: "0.1.0"
   mode: instructive
   origin:
     kind: local-path
     path: /ruta/origen
     imported_at: "2026-10-22T..."
   scripts: []
   scripts_executed_on_import: false
   file_sha256:
     SKILL.md: <sha256>
   warnings: []
   ```

6. Confirma por pantalla que **ningún archivo fue ejecutado durante la
   importación** y sugiere el comando `skills enable`.

Verificado en el entorno: importar una skill con symlink falla con
`Importación rechazada: Symlink rechazado: <ruta>`, y los archivos copiados
quedan con permisos `-rw-r--r--` (sin `x`).

## Validación (`skills validate`)

```bash
design-pipeline skills validate mi-skill -p <proyecto>   # por nombre registrado
design-pipeline skills validate ./mi-skill               # por carpeta local
```

Devuelve `VÁLIDA`/`INVÁLIDA` (exit `0`/`1`) con la lista de errores y avisos.
Errores: sin `SKILL.md`, frontmatter inválido, nombre inválido o
discrepante, `description` vacía, `mode` desconocido, `stages` con ids
desconocidos, scripts inseguros o inexistentes. Avisos: modo `executive`,
scripts declarados (con recordatorio de que no se ejecutan), cuerpo muy corto
(menos de 40 caracteres), permisos no estándar.

## Permisos, habilitación y modos

- **Habilitar es una acción por proyecto:**
  `design-pipeline skills enable <nombre> -p <proyecto>` agrega el nombre a
  `skills.enabled` en `project.yaml`; `skills disable` lo quita. Ambos
  requieren `--project`.
- **Semilla en `init`:** al crear un proyecto, `seed_internal_skills` habilita
  todas las skills internas. Es el único momento en que algo se habilita sin
  inspección previa, porque son instrucciones del propio paquete.
- **`mode: executive` necesita doble gate:** importarla (`skills add`) y
  habilitarla (`skills enable`, también desde la TUI) exigen
  `skills.allow_executive: true` en la configuración efectiva. Sin eso, el
  comando falla con un mensaje que indica la clave a activar. Aun así, una
  skill executive **nunca ejecuta scripts sola**: `scripts` solo se lista para
  inspección.
- **Activación por etapa:** al hacer `Pipeline.begin()` de una etapa, el motor
  registra en el log el evento `skills_activated` con las skills habilitadas
  que declaran esa etapa en `stages`, y lo anota en las `notes` de la etapa.
  Es trazabilidad pura: no se ejecuta ni se inyecta código.
- **Eliminación:** `skills remove <nombre> -p <proyecto> --yes` es
  destructivo y **exige `--yes`**; además borra el nombre de
  `skills.enabled`. Las skills `internal` no se pueden eliminar.

## Precedencia de instrucciones

Cuando las instrucciones se contradicen, el orden es (documentado en el
docstring de `skills/registry.py` y aplicado por los consumidores):

1. **principios del sistema y controles de seguridad**
   (`src/design_pipeline/data/principles/`: `fidelity.md`, `safety.md`,
   `traceability.md`, `human-review.md`);
2. **reglas aprobadas del proyecto** (`rules/design-rules.yaml` en estado
   `approved`);
3. **recomendaciones de skills externas** (cualquier skill de origen
   `global` o `project`).

Una skill externa es contenido a revisar, no una fuente de autoridad: si su
cuerpo pide modificar la exportación, saltar aprobaciones o instalar
dependencias, prevalecen los principios y la seguridad por defecto.

## Skills internas del paquete

Cinco skills instructivas en `src/design_pipeline/data/skills/`, todas
`version: 1.0.0`, `format: markdown-folder`, `mode: instructive`, `scripts: []`
y habilitadas por defecto en cada proyecto nuevo:

| Skill | `stages` | `permissions` | Qué cubre |
| --- | --- | --- | --- |
| `inspect-design` | `[import]` | `read-workspace`, `write-reports` | Recorrer la exportación, clasificar archivos, detectar componentes/assets/dependencias/duplicados/referencias rotas sin ejecutar ni modificar nada |
| `analyze-batch` | `[analyze]` | `read-workspace`, `write-reports` | Analizar componentes, props/estados/variantes, tokens, accesibilidad, duplicaciones; clasificar hallazgos y registrar incertidumbres |
| `define-design-rules` | `[rules]` | `read-workspace`, `write-reports`, `write-rules` | Formular preguntas priorizadas y convertir respuestas en reglas trazables con procedencia y estado |
| `generate-components` | `[spec, generate]` | `read-workspace`, `write-specs`, `write-output` | Producir la especificación fiel y generar código por perfil respetando props, nombres y estilos observados |
| `validate-output` | `[validate, report]` | `read-workspace`, `read-output`, `write-reports` | Validar con evidencia, distinguir PASS/FAIL/SKIPPED/NEEDS_REVIEW y preparar la revisión humana final |

Inspección recomendada antes de tocar nada:

```bash
design-pipeline skills inspect inspect-design -p <proyecto>
design-pipeline skills validate inspect-design -p <proyecto>
```

## Limitaciones

- Las skills no tienen lenguaje de programación ni hooks: son texto. El
  pipeline solo las lista, las asocia a etapas y las registra en el log.
- `permissions` no otorga capacidades reales: es declarativa (los permisos
  fuertes del sistema son los flags y claves de configuración de
  `docs/SECURITY.md`).
- No hay mecanismo de actualización: para reemplazar una skill hay que
  `skills remove ... --yes` y volver a `skills add` (nunca se sobrescribe).
- La habilitación vive en el `project.yaml` de cada proyecto; no existe
  habilitación global para todas las carpetas.
