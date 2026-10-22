---
name: generate-components
description: "Guía para producir la especificación intermedia fiel al diseño y generar código por perfil de destino respetando props, nombres y estilos observados."
version: 1.0.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, write-specs, write-output]
tools: []
stages: [spec, generate]
scripts: []
---

# Generar componentes

Objetivo: cubrir las etapas `spec` y `generate`: traducir el análisis a una especificación independiente del framework y luego a código para el perfil elegido (`react-css` o `astro-css`), conservando la fidelidad del diseño de origen.

## Etapa spec: especificación intermedia

1. Producir una especificación por componente con: identidad y propósito, props con defaults, estados, variantes, jerarquía estructural, tokens usados, dependencias y recursos, reglas responsive, interacciones y accesibilidad.
2. Incluir restricciones de fidelidad: valores que no deben alterarse (colores, medidas, textos) y sus procedencias (archivo y línea).
3. Incluir relaciones con otros componentes del lote y las reglas aprobadas que aplican.
4. Incluir dudas abiertas: lo que quedó Pendiente o NEEDS_REVIEW, sin resolverlo dentro de la especificación.
5. Mantener consistentes entre sí el formato legible (Markdown) y el formato procesable (JSON/YAML).
6. La especificación debe ser suficiente para generar sin volver a analizar todo el lote mientras siga vigente (mismos hashes de entrada y reglas).

## Etapa generate: código por perfil

1. Respetar nombres de componentes, props, estados y textos observados, salvo regla aprobada o imposibilidad técnica documentada.
2. Aplicar los estilos desde la especificación: colores, tipografías, espaciados y medidas exactos. Sin redondeos ni normalizaciones no aprobadas.
3. Evitar estilos globales involuntarios: CSS acotado al componente según la convención del perfil, sin resets globales ni cambios a selectores ajenos.
4. Evitar imports rotos: cada import de recurso, componente o paquete debe resolver dentro de la estructura generada o corresponder a una dependencia declarada y aprobada.
5. En `react-css`: generar componentes con props y composición equivalentes a la especificación, con CSS asociado por componente.
6. En `astro-css`: convertir a Astro solo componentes estáticos. Para componentes con interactividad (estado, eventos, efectos), generar una isla React con fallback explícito, preservando el mismo marcado y estilos; documentar la conversión.
7. Si la especificación marca un valor como NEEDS_REVIEW, no elegir por cuenta propia: dejar el marcador visible en el código generado y en el reporte de generación.
8. No instalar dependencias automáticamente: listar lo que el código generado requiere y pedir aprobación.
9. La conversión a Tailwind no está implementada de forma determinista: informar la limitación en lugar de simularla.

## Criterio de salida

- Cada componente generado tiene rutas de especificación y reglas aplicadas identificables.
- Props, nombres y textos coinciden con la especificación; ningún estilo global introducido.
- Los NEEDS_REVIEW quedan visibles en código y reporte, no silenciados.

## Salidas

- `specs/<componente>/spec.md` y `specs/<componente>/spec.json` (o YAML): especificación intermedia por componente.
- `output/<perfil>/`: código generado por componente, CSS asociado y README por componente o grupo cuando ayude a explicar uso, props, variantes y limitaciones.
- Reporte de generación: conversiones realizadas, decisiones tomadas, NEEDS_REVIEW y dependencias propuestas.
