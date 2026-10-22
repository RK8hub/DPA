---
name: define-design-rules
description: "Guía para formular preguntas de descubrimiento priorizadas y convertir respuestas humanas en reglas de diseño con procedencia y estado."
version: 1.0.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, write-reports, write-rules]
tools: []
stages: [rules]
scripts: []
---

# Definir reglas de diseño y preguntas

Objetivo: sostener la etapa `rules` en modo descubrimiento: transformar el análisis en preguntas concretas para el humano y sus respuestas en reglas trazables. El modo guiado (reglas provistas al inicio) sigue el mismo formato de registro.

## Formular preguntas

1. Partir de `reports/ANALYSIS.md`, `COMPONENT-MAP.md` y `uncertainties.md`: las preguntas nacen de hallazgos y dudas reales del lote, no de una lista genérica.
2. Agrupar por tema: framework y destino, convenciones de nombres, estructura de archivos, tokens, responsive, accesibilidad, reutilización, dependencias.
3. Priorizar por impacto en la generación: primero lo que cambia código (perfil de destino, tratamiento de interactivos, tokens), después convenciones.
4. Formular cada pregunta de forma concreta y acotada al lote. Cuando sea útil, ofrecer opciones con una recomendación explicada en una línea.
5. Aceptar respuestas parciales: registrar lo respondido y mantener lo restante como Pendiente.
6. No incluir en las preguntas decisiones que los principios del sistema ya resuelven (por ejemplo, si está permitido modificar la exportación original).

## Convertir respuestas en reglas

1. Cada respuesta aceptada se escribe en `rules/design-rules.yaml` con:
   - identificador estable;
   - enunciado de la regla;
   - estado: `proposed` hasta aprobación, `approved` después;
   - procedencia: pregunta que la originó y hallazgo asociado (archivo y línea cuando aplique);
   - alcance: componentes, perfiles o valores a los que aplica.
2. Registrar en `reports/DECISIONS.md` cada respuesta: qué se decidió, quién, cuándo y cómo (respuesta a pregunta, o aprobación explícita posterior).
3. Reflejar las reglas aprobadas en `reports/DESIGN-RULES.md` en lenguaje legible, con estado y procedencia visibles.
4. Generar propuestas de regla cuando el análisis las sugiera (Propuesto), marcadas como `proposed` hasta aprobación humana.
5. No modificar los principios centrales del sistema al crear reglas de proyecto: si una respuesta entra en conflicto con un principio, señalarlo y no aplicarla.

## Después de las respuestas

- Verificar coherencia: reglas que se contradicen entre sí se marcan como Pendiente para resolución humana.
- Confirmar que toda regla `approved` tiene decisión asociada en `DECISIONS.md`; si no, no se considera vigente.
- Listar en el resumen qué preguntas quedaron pendientes y cómo afectan la generación (qué decisiones implícitas asumiría el perfil por defecto).

## Criterio de salida

- Cada regla con estado y procedencia; cada decisión con quién, cuándo y cómo.
- Ninguna regla `approved` sin registro de aprobación.
- Las dudas no resueltas siguen visibles en `uncertainties.md`.

## Salidas

- `rules/design-rules.yaml`: reglas con identificador, estado, procedencia y alcance.
- `rules/questions.yaml`: preguntas formuladas, opciones, recomendación y respuesta (o pendiente).
- `reports/DESIGN-RULES.md`: versión legible de las reglas con estado.
- `reports/DECISIONS.md`: registro de respuestas y aprobaciones.
