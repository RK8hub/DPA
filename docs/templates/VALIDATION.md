<!-- Plantilla de referencia para reports/VALIDATION.md (etapa G) -->
<!-- Los archivos reales se generan desde ValidationReport con
     validators/runner.py:render_validation_markdown() (y su gemelo machine
     reports/validation-report.json). Esta plantilla solo explica la
     estructura: los estados se obtienen de ejecutar `validate`. -->

# Validación

- **Fecha:** {{created_at — ISO-8601 UTC}}
- **Perfil:** `{{react-css | astro-css}}`
- **Veredicto:** `{{pass | pass_with_review | fail}}`
- **Resumen:** PASS {{n}} · FAIL {{n}} · SKIPPED {{n}} · NEEDS_REVIEW {{n}}

<!-- Por cada check, en el orden en que run_validate() los ejecuta:
     integrity, isolation, spec-schema, manifests, references, class-coverage,
     accessibility, framework-integration, external-build, responsive, visual.
     El renderizador real precede cada estado con un símbolo gráfico
     correspondiente; acá se representa con {{marca}}. -->

## {{marca}} {{PASS | FAIL | SKIPPED | NEEDS_REVIEW}} — {{nombre del check}}

- **Detalle:** {{qué se comprobó y cuál fue el resultado, o el motivo exacto si no se ejecutó}}
- **Evidencia:** `{{JSON resumido — p. ej. {"files": 14} o {"cmd": [...], "exit_code": 0}}`
- **Limitación:** {{límite declarado del check, cuando aplica}}

## {{marca}} {{estado}} — {{Integridad de archivos de salida}}

- **Detalle:** {{n}} archivos verificados; estructura completa.

## {{marca}} {{estado}} — {{Aislamiento de la fuente}}

- **Detalle:** {{la huella de la exportación coincide / cambió / la fuente ya no existe}}
- **Evidencia:** `{{fingerprint[:16]}}…`

<!-- ... un bloque idéntico por cada uno de los 11 checks. Las líneas
     "Evidencia" y "Limitación" solo aparecen si el check las tiene. -->

## Recordatorio

- Los estados SKIPPED y NEEDS_REVIEW **no** significan que la comprobación
  pasó: significan que no se ejecutó o que requiere revisión humana.

<!-- Reglas de lectura (obtenidas de validators/runner.py):
     - PASS solo con ejecución registrada; jamás implícito.
     - SKIPPED = no ejecutado, con el motivo siempre escrito (herramienta
       ausente, falta de --approve-external + config, no aplica...).
     - NEEDS_REVIEW = requiere criterio humano.
     - Veredicto: fail si hay algún FAIL; pass_with_review si hay algún
       NEEDS_REVIEW (y ningún FAIL); pass en el resto.
     - responsive y visual son SKIPPED en esta versión (sin ejecutor de
       navegador ni captura): no es una aprobación.
     - El mismo contenido está en reports/validation-report.json (y en el
       --json del comando validate) para leerlo en máquina. -->
