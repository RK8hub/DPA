<!-- Plantilla de referencia para reports/DECISIONS.md (etapa D) -->
<!-- Los archivos reales se generan desde rules/questions.yaml y
     rules/design-rules.yaml con rules/manager.py:render_rules_reports().
     Regenerado desde los datos máquina; editar directamente no tiene efecto
     (usar `rules answer` / `rules approve`). -->

# Decisiones del proyecto

Registro de respuestas, procedencia y estado. Regenerado desde los datos
máquina; editar directamente no tiene efecto (usar los comandos
`rules answer` / `rules approve`).

## Preguntas

### {{q-001}} ({{categoría — destino, estilos, tokens, interactividad, accesibilidad, reutilizacion, análisis:...}}) — {{open | answered | postponed}}

- Pregunta: {{texto de la pregunta}}
- Procedencia: {{discovery | discovery+<incertidumbre-id> | archivo-reglas#hash | análisis:<incertidumbre-id>}}
- Respuesta: `{{valor}}` (registrada {{fecha ISO-8601 UTC}})
- Opciones: `{{valor1}}`, `{{valor2}}`
- Recomendación: `{{valor-recomendado}}`

<!-- Reglas del render:
     - La línea "Respuesta" solo aparece si la pregunta tiene respuesta.
     - Las líneas "Opciones" y "Recomendación" solo aparecen si existen.
     - Estados posibles: open (sin responder), answered, postponed
       (`rules answer --postpone`).
     - Sin preguntas registradas: "- Sin preguntas registradas (modo guiado o
       etapa no ejecutada)." -->

### {{q-002}} ({{categoría}}) — {{answered}}

- Pregunta: {{texto}}
- Procedencia: {{fuente}}

## Reglas

- **{{r-001}}** [{{proposed | approved | rejected}}] ({{categoría}}) — {{enunciado de la regla}}
  - Procedencia: {{kind — user | derived}} → `{{origin — archivo#hash | answer:q-001}}`{{; decisión: {{quién}} {{fecha}} si ya se decidió}}

- **{{r-002}}** [{{estado}}] ({{categoría}}) — {{enunciado}}
  - Procedencia: {{kind}} → `{{origin}}`

<!-- Reglas del render:
     - Sin reglas: "- Sin reglas registradas."
     - La línea de decisión solo aparece cuando la regla tiene decided_at.
     - Los ids siguen el patrón r-001, r-002, ... y las preguntas q-001, ...
     - El orden es el de los archivos YAML, no por estado. -->

<!-- Notas de lectura:
     - state.decisions_pending refleja las preguntas open y las reglas
       proposed: lo ves en `status` y en el CONTEXT.md.
     - Toda pregunta respondida deriva una regla `proposed` con procedencia
       `answer:<id>`; la regla recién se aplica si el usuario la aprueba con
       `rules approve`. Acá queda la respuesta y su trazabilidad.
     - "Procedencia" es la cadena de trazabilidad: hallazgo → pregunta →
       respuesta → regla. -->
