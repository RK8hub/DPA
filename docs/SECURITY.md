# Seguridad

Este documento describe los límites de confianza **reales** de la
implementación: qué controla el sistema, cómo y con qué puertas. Los principios
completos viven en `src/design_pipeline/data/principles/` (`fidelity.md`,
`safety.md`, `traceability.md`, `human-review.md`) y este archivo resume lo
aplicable con código verificable.

## Modelo de confianza

| Elemento | Confianza | Cómo se controla |
| --- | --- | --- |
| Exportación original | Solo lectura, fuente de verdad | Nunca se escribe en ella; huella (`tree_fingerprint`) verificada después en el check `isolation` |
| Workspace del proyecto | Zona de escritura propia | Toda escritura cae en `<workspace>/<proyecto>/` |
| Skills externas | Contenido no confiable | Copia validada, sin bit de ejecución, sin symlinks, límites de tamaño, doble gate `executive`, nunca ejecutadas |
| Comandos externos (`validate`) | Peligroso | Doble permiso + `package.json` + `npm`; si falta algo: `SKIPPED` |
| CLIs de agente | Peligroso | Doble permiso + detección informativa; salida redactada y acotada |
| Configuración del usuario/proyecto | Controlada por la persona | Fusión documentada; sin auto-ejecución |

## La exportación original es de solo lectura

- `importers/stage.py` solo lee: escribe `inventory.json` y
  `reports/IMPORT-REPORT.md` **dentro del proyecto**, nunca en la carpeta de
  origen. `iter_files` (`utils.py`) camina con `followlinks=False` y descarta
  symlinks (de directorio y de archivo), así que no se escapa del árbol.
- La huella del árbol de origen se guarda en `inventory.json`
  (`source_fingerprint`) y se vuelve a calcular en la etapa `validate`:
  - coincide → check `isolation` en `PASS`;
  - cambió → `FAIL` con "La exportación original cambió después de importarse"
    (y las etapas aguas abajo quedan `stale` por los fingerprints);
  - la fuente ya no existe → `NEEDS_REVIEW`.
- Ningún archivo de entrada se ejecuta jamás (ni scripts, ni binarios, ni
  shebangs): se analizan como texto. `IMPORT-REPORT.md` lo declara en su
  sección "Notas de seguridad".
- Los patrones de `exclusions` además dejan fuera del inventario `.env*`,
  `*.pem`, `id_rsa*`, `credentials*` y `secrets*`.

## Skills externas: contenido no confiable

Resumen de los controles (detalle y comandos en `docs/SKILLS.md`):

- **Nunca se ejecutan.** `skills add` solo copia bytes y calcula hashes;
  `scripts_executed_on_import: false` queda escrito en `skill.yaml` y los
  scripts declarados se listan con el aviso "NO se ejecutará automáticamente".
- **Sin bit de ejecución:** la copia usa `write_bytes` (permisos `rw-r--r--`
  por defecto), no hereda los del origen. Verificado en el entorno.
- **Sin symlinks, sin archivos ocultos, sin traversal:** `_safe_copy_tree`
  rechaza cualquier componente de ruta que empiece con `.`, cualquier symlink
  y tipos que no sean archivo/carpeta; los `scripts` con ruta absoluta o `..`
  hacen fallar la validación.
- **Límites de tamaño:** 2 MB por archivo y 20 MB por skill; ante un rechazo,
  la importación se limpia y falla.
- **Doble gate para `mode: executive`:** importar (`skills add`) y habilitar
  (`skills enable`, también en la TUI) exigen
  `skills.allow_executive: true`; sin eso, error explícito.
- **Habilitación por proyecto:** nada queda activo solo por existir; la lista
  `skills.enabled` vive en el `project.yaml` y `skills remove` exige `--yes`.
  Las skills internas no se pueden eliminar.
- **Precedencia:** principios y controles de seguridad > reglas aprobadas >
  recomendaciones de skills externas. Una skill externa no puede autorizarse a
  sí misma a hacer nada que los principios prohíben.
- Al inicio de cada etapa, el motor registra en el log qué skills habilitadas
  declaran esa etapa (`skills_activated`): solo trazabilidad.

## Ejecución externa con doble permiso

No hay ningún camino de ejecución que dependa de un solo interruptor.

### Comandos de build/lint (`validate`)

El check `external-build` (`validators/runner.py`) solo ejecuta
`npm run --silent build` dentro de `output/<perfil>/` si se cumplen **todas**
estas condiciones:

1. existe `package.json` en la salida (los perfiles actuales generan archivos
   sueltos, por lo que en la práctica el check se saltea con ese motivo);
2. flag `--approve-external` en la CLI (o en `resume`/TUI);
3. `validation.approve_external_commands: true` en la configuración;
4. `npm` disponible en el `PATH`.

Si falta cualquiera, el resultado es `SKIPPED` **con el motivo escrito** en
`VALIDATION.md`. Cuando corre, registra comando, `exit_code`, duración y cola
de `stderr` como evidencia, con timeout de 300 s.

### Ejecución de agentes (`agent run`)

Doble permiso obligatorio: `agent.allow_execution: true` en la configuración
**y** el flag `--allow-execution`. Además:

- el adaptador debe estar declarado en `agent.adapters` (no se puede improvisar
  un comando en la CLI);
- el ejecutable debe existir en `PATH`;
- se corre **sin shell** (`subprocess.run` con lista de argumentos);
- el entorno recibido por el subprocess es mínimo: `PATH`, `HOME` y
  `LANG=C.UTF-8` (no se hereda el entorno completo);
- timeout de 300 segundos;
- stdout/stderr pasan por la redacción antes de persistirse; el comando se
  redacta también en el archivo de resultado;
- cada corrida deja `runs/<run_id>.jsonl` (`agent_run_requested`,
  `command`, o `agent_run_blocked`) y un bloque en `logs/summary.md`.

Detalle y límites de honestidad (solo stub probado, sin adaptadores
pre-declarados) en `docs/AGENT-ADAPTERS.md`.

### Lo que nunca instala ni modifica

- **No se instalan dependencias.** Ni `pip`, ni `npm install`, ni `npx astro
  add`: los requisitos (React, `@astrojs/react`, etc.) se listan en los README
  de salida y en `generation-notes.md` para que los instale una persona en el
  proyecto destino. El único comando externo ejecutable es el build descrito
  arriba.
- No se modifican configuraciones globales del sistema ni de otras
  herramientas, ni archivos fuera del workspace del proyecto.

## Redacción de secretos

Dos capas en `utils.py`, aplicadas a todo lo que se persiste o se loguea:

1. **Por clave estructurada — `redact(value)`:** recorre dicts/listas y
   reemplaza por `***REDACTED***` cualquier valor cuya clave coincida con
   `(?i)(token|secret|password|passwd|api[_-]?key|authorization|credential|private[_-]?key|session)`.
   Los strings restantes pasan por la capa 2.
2. **Por contenido — `redact_text(text)`:** enmascara patrones dentro de texto
   libre (salidas de agentes, stderr, comandos):
   - llaves privadas completas (`-----BEGIN ... PRIVATE KEY-----` a
     `-----END ...`);
   - tokens tipo `sk-` / `pk-` / `rk-` (16+ caracteres);
   - tokens de GitHub `ghp_` y `github_pat_`;
   - claves de AWS `AKIA` + 16 dígitos;
   - JWTs (`eyJ....eyJ....`);
   - `Bearer <token>`;
   - pares `authorization|api_key|access_token|password|passwd|secret`
     seguidos de `:`/`=` y un valor.

Todo evento del `RunLogger` pasa por `redact()` antes de escribirse, y la
salida de los adaptadores se redacta por separado en stdout, stderr y comando.

Existe además `redact_env(env)` (filtra claves sensibles del entorno y trunca
valores), usada por las pruebas; en los caminos productivos no hace falta
porque **el entorno completo nunca se registra**.

## Logs sin secretos ni entorno completo

- `runs/<run_id>.jsonl`: una línea JSON por evento con `ts`, `run_id`,
  `stage`, `type` y campos propios, todos redactados. El docstring de
  `engine/log.py` lo explicita: "Nunca registra variables de entorno
  completas ni valores bajo claves sensibles".
- `logs/summary.md`: bloques humanos por ejecución (con rutas, conteos y
  estados; sin entorno ni secretos).
- `state.yaml`: estados, artefactos, notas y fingerprints (hashes), no valores
  de configuración sensibles.
- El prompt que recibe un agente se guarda con su **prefijo sha256** en el
  log, no con su texto.

Nota honesta: la redacción es por patrones. Un secreto con un formato
desconocido y bajo una clave no sensible podría atravesarla; por eso los
permisos de ejecución son explícitos y los archivos de resultado quedan en el
workspace, a la vista.

## TUI

- La TUI no ingresa comandos arbitrarios ni ejecuta agentes: no existe ninguna
  opción de `agent run` en sus menús, y `skills` en la TUI solo alterna la
  habilitación (con el gate `skills.allow_executive` para `executive`).
- El único comando externo que la TUI puede disparar es el `npm run build` del
  check `external-build` de `validate`, y solo en el flujo "Ejecutar pipeline
  hasta la entrega" si la persona confirma (`¿Permitir comandos externos
  (build/lint) en validate?`, default **no**) **y** la configuración lo
  autoriza **y** existe `package.json`. Al ejecutar una etapa suelta desde la
  TUI, `approve_external` queda en `False`.
- Las confirmaciones de la TUI son del usuario: la TUI no aprueba nada por
  cuenta propia (generar código pide confirmación con default "no").

## Confirmaciones destructivas

- `skills remove <nombre> ... --yes`: sin `--yes` falla con "Eliminar una
  skill es destructivo: repetí el comando con --yes para confirmar.".
- No hay otros comandos destructivos: el pipeline no borra la exportación ni
  artefactos de corridas anteriores (`runs/` y `reports/` se sobrescriben por
  nombre de etapa, con escritura atómica en los YAML).

## Principios de referencia

En `src/design_pipeline/data/principles/`:

- `safety.md` — seguridad por defecto: fuente de solo lectura, skills como
  contenido no confiable, aprobación explícita para ejecutar, secretos y
  logs, límites honestos (incluye la ausencia de sandbox).
- `human-review.md` — qué requiere aprobación humana y qué puede avanzar solo.
- `traceability.md` — procedencia de hallazgos, decisiones, validaciones y
  logs (qué es `PASS` sin ejecución: no existe).
- `fidelity.md` — fidelidad antes que reinterpretación: la exportación define
  el resultado.

## Límites honestos

- **No hay sandbox de procesos.** El aislamiento real depende del SO y del
  entorno de la persona. El sistema previene ejecución no autorizada por
  política (permisos, validación de rutas) pero no puede neutralizar código
  que alguien aprueba ejecutar explícitamente.
- La redacción es por patrones y puede cubrir formatos de secreto no previstos.
- No hay verificación de integridad firmada de las skills: el `digest` detecta
  cambios, no prueba autoría.
- El validador de esquemas es un subconjunto de JSON Schema (ver
  `docs/ARCHITECTURE.md`).
- `validate` no ejecuta pruebas de navegador ni comparación visual: esos
  checks son `SKIPPED` y su ausencia **no** es una garantía de seguridad ni de
  fidelidad.

## Criterio de salida

- Ninguna ejecución de código externo ni escritura fuera del workspace ocurrió
  sin aprobación registrada.
- Ningún artefacto del proyecto registra variables de entorno completas ni
  secretos bajo claves sensibles (sí aplica redacción por contenido).
- La exportación original queda verificada como intacta por el check
  `isolation`.
