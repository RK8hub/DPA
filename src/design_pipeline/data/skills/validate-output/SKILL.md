---
name: validate-output
description: "Guía para validar el output con evidencia registrada, distinguir PASS/FAIL/SKIPPED/NEEDS_REVIEW y preparar la revisión humana final."
version: 1.0.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, read-output, write-reports]
tools: []
stages: [validate, report]
scripts: []
---

# Validar y reportar

Objetivo: cubrir las etapas `validate` y `report`: ejecutar las validaciones disponibles con evidencia registrada y producir el informe de entrega con la checklist de revisión humana. La validación compara contra la especificación y el diseño de origen, no contra una noción estética.

## Reglas de evidencia

- Nunca escribir PASS sin ejecución registrada: comando, código de salida, versión de la herramienta y limitaciones van juntos en `reports/VALIDATION.md`.
- Si una herramienta necesaria no está instalada, registrar el requisito ausente y el estado SKIPPED con el motivo; continuar con las comprobaciones restantes cuando sea seguro.
- Si una comprobación depende de criterio humano o de herramientas no disponibles (comparación visual, pruebas responsive manuales), el estado es NEEDS_REVIEW o SKIPPED, nunca PASS.
- Un test generado por el agente no se considera aprobado por existir: necesita ejecución registrada.

## Estados

- **PASS:** ejecutado, sin hallazgos, evidencia adjunta.
- **FAIL:** ejecutado, con hallazgo que impide considerar válido el resultado; incluir evidencia y ubicación.
- **SKIPPED:** no ejecutado por herramienta ausente, decisión registrada o falta de referencia; incluir motivo.
- **NEEDS_REVIEW:** requiere criterio humano (fidelidad visual, accesibilidad subjetiva, ambigüedad residual).

## Validaciones a cubrir

1. Integridad de archivos y estructura del output según el perfil.
2. Validez de JSON/YAML y cumplimiento de esquemas.
3. Existencia de imports y recursos referenciados, sin referencias rotas.
4. Lint, type-check y build cuando el proyecto de destino lo permita, previa aprobación para ejecutar comandos externos.
5. Pruebas funcionales solo cuando haya comportamiento verificable.
6. Pruebas responsive en viewports configurables, cuando existan herramientas; si no, SKIPPED con el motivo.
7. Pruebas de accesibilidad automatizables disponibles en el entorno.
8. Capturas y comparación visual solo con herramientas y referencias disponibles; sin ellas, SKIPPED. No se prometen pruebas visuales automáticas.

## Checklist de revisión humana

- Armar `reports/REVIEW-CHECKLIST.md` con: componentes generados, archivos de explicación, reglas y decisiones aplicadas, pruebas ejecutadas y su resultado, pruebas omitidas y motivo, advertencias y limitaciones, y diferencias relevantes respecto de la fuente.
- Cada ítem queda como pendiente de revisión humana; el cierre lo hace una persona antes de copiar el output al proyecto real.
- La entrega se declara lista solo con la checklist revisada y cerrada.

## Criterio de salida

- `VALIDATION.md` sin PASS sin evidencia; cada resultado con estado, comando y limitación.
- El informe final distingue con claridad qué se verificó, qué no y por qué.

## Salidas

- `reports/VALIDATION.md`: resultados por validación con estado, evidencia y limitaciones.
- `reports/REVIEW-CHECKLIST.md`: lista de revisión humana por cerrar.
- Resumen de entrega (etapa `report`): ruta de `output/<perfil>/`, componentes, pruebas ejecutadas y omitidas, advertencias y diferencias respecto de la fuente.
