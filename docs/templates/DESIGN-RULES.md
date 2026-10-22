<!-- Plantilla de referencia para reports/DESIGN-RULES.md (etapa D) -->
<!-- Los archivos reales se generan desde rules/design-rules.yaml con
     rules/manager.py:render_rules_reports(), de forma idempotente. Editar el
     Markdown real no tiene efecto: las reglas se crean con `rules init`,
     `rules answer` y `rules approve`. -->

# Reglas de diseño

Actualizado: {{fecha ISO-8601 UTC de la última regeneración}}

Las reglas `proposed` todavía no se aplican. Aprobá con
`design-pipeline rules approve --id <regla>` (o `--all`).

## Aprobadas (se aplican en spec/generate)

- **{{r-001}}** ({{categoría — p. ej. destino, estilos, guiada}}): {{enunciado de la regla}}

<!-- Sección con las reglas en estado approved. Son las únicas que la etapa
     spec agrega a `applied_rules` y que generate respeta. Vacía: "- (ninguna)". -->

## Propuestas (pendientes de aprobación)

- **{{r-002}}** ({{categoría}}): {{enunciado — todavía NO se aplica}}

<!-- Reglas creadas por respuestas (derive_rules_from_answers), por el modo
     guiado sin --approve, o marcadas como Propuesto en el análisis. Vacía:
     "- (ninguna)". -->

## Rechazadas

- **{{r-003}}** ({{categoría}}): {{enunciado rechazado con `rules approve --reject`}}

<!-- Vacía: "- (ninguna)". -->

<!-- Notas de lectura:
     - Cada línea del archivo real es `- **<id>** (<categoría>): <texto>`.
     - El estado completo (con procedencia y quién/cuándo decidió) está en
       reports/DECISIONS.md y en rules/design-rules.yaml.
     - Las reglas `proposed` aparecen en DELIVERY.md como "Reglas pendientes
       (no aplicadas)" y en REVIEW-CHECKLIST.md como ítems de revisión. -->
