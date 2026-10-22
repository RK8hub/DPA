# Humano en el circuito

El pipeline asiste, no decide en nombre del usuario. Donde hay ambigüedad, cambio normativo o riesgo, la ejecución se detiene y consulta. Este documento define qué requiere aprobación humana y qué puede avanzar solo.

## Requiere aprobación explícita

- **Reglas de diseño nuevas:** ninguna regla pasa a estado aprobada sin confirmación humana, aunque el agente la haya recomendado.
- **Respuestas a preguntas de descubrimiento:** las respuestas del usuario a las preguntas de la etapa `rules` son la fuente de las reglas. Una respuesta parcial deja lo restante como Pendiente y no se completa por cuenta propia.
- **Ejecución de código externo:** cualquier script, comando de build/lint/type-check o instalación de dependencias se muestra completo y se aprueba antes de correr.
- **Habilitación de skills ejecutivas:** una skill que declara scripts o permisos de escritura requiere inspección previa y habilitación aprobada.
- **Uso del perfil por defecto con reglas pendientes:** si hay preguntas Pendiente sin resolver, generar con el perfil por defecto solo tras avisar qué decisiones quedan implícitas y obtener confirmación.
- **Copia del output al proyecto real:** completar `reports/REVIEW-CHECKLIST.md` es condición previa a declarar la entrega lista. La checklist la revisa y cierra una persona.

## Puede proceder sin aprobación

- Inventario de la exportación (`inventory.json`, reporte de importación): es lectura y registro, no altera la fuente.
- Análisis observacional de la etapa `analyze`: informes que separan Observado, Inferido, Propuesto y Pendiente.
- Especificación intermedia de la etapa `spec`: traducción fiel del análisis, sin decisiones nuevas.
- Validaciones deterministas de la etapa `validate` que no ejecutan código externo: integridad de archivos, validez de JSON/YAML y esquemas, existencia de imports y recursos referenciados.
- Generación de código en el workspace de salida, siempre que respete especificación y reglas aprobadas y no instale dependencias.

## Cómo consultar

- Las preguntas deben ser concretas, agrupadas y priorizadas, con opciones y una recomendación explicada cuando sea útil.
- Se aceptan respuestas parciales: lo respondido se registra como decisión; lo restante queda como Pendiente en `reports/uncertainties.md`.
- El sistema debe distinguir en sus salidas qué elementos quedaron aprobados por un humano y cuáles son propuestas sin validar.

## Aprobaciones en modo no interactivo

- En modo no interactivo no hay consulta en línea: si una etapa requiere aprobación, se pausa y deja el estado como esperando decisión, con la pregunta y las opciones listadas para que el humano responda al reanudar.
- No se debe simular una aprobación por defecto para destrabar una ejecución automatizada. El perfil por defecto solo se usa con reglas pendientes tras el aviso y la confirmación descritos arriba.
- Las respuestas cargadas al reanudar se registran con la misma procedencia que las respuestas interactivas (quién, cuándo, cómo).

## Registro de aprobaciones

- Toda aprobación queda en `reports/DECISIONS.md` con fecha y ejecución de referencia; las reglas aprobadas se marcan en `rules/design-rules.yaml`.
- Las aprobaciones son por proyecto: no se propagan a otros proyectos ni sobreviven a un cambio de reglas que las invalide.
- Si una aprobación posterior contradice una decisión anterior, se registra la nueva y se marca la anterior como obsoleta, sin borrarla.

## Criterio de salida

- Toda regla vigente, ejecución de código y entrega final tiene una aprobación humana registrada con fecha y ejecución de referencia.
- Ningún resultado del pipeline se presenta como definitivo cuando contiene elementos Pendiente o NEEDS_REVIEW sin señalarlo.
