---
name: analyze-batch
description: "Guía para analizar el lote importado: componentes, relaciones, props, tokens, accesibilidad e incertidumbres, con clasificación de hallazgos."
version: 1.0.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, write-reports]
tools: []
stages: [analyze]
scripts: []
---

# Analizar el lote

Objetivo: producir el análisis de la etapa `analyze` a partir del inventario y los archivos de la exportación, sin ejecutar código y sin modificar la fuente. Preparar un paquete de contexto acotado: texto de archivos relevantes, no binarios.

## Qué analizar

1. **Componentes y relaciones:** para cada componente, imports de otros componentes del lote, composición vía children o props y jerarquía resultante. Registrar en `COMPONENT-MAP.md`.
2. **Props, estados y variantes:** listar props declaradas con sus defaults observados, estados (hover, disabled, open, etc.) y variantes visuales (modificador, prop booleana, tamaño). Distinguir variante visual de componente distinto.
3. **Tokens y estilos:** colores (hex, rgb, variables), tipografías (familias, tamaños, pesos, interlineado), espaciados, medidas, radios, sombras y breakpoints. Registrar valores exactos con archivo y línea.
4. **Recursos e imports:** assets y fuentes referenciados, dependencias externas declaradas en los archivos.
5. **Duplicaciones aparentes:** componentes o bloques de estilo muy similares. Reportar similitud y diferencias concretas; no declararlos intercambiables sin evaluar props, estados y comportamiento.
6. **Accesibilidad y semántica:** uso de elementos, roles, atributos ARIA, texto alternativo en imágenes, contraste aparente, foco y navegación por teclado. Marcar problemas como Observado o Inferido con justificación.
7. **Limitaciones de la exportación:** archivos rotos, estilos ausentes, componentes que parecen incompletos.

## Clasificación de hallazgos

- **Observado:** respaldado por contenido de archivos, con referencia (archivo, línea cuando sea posible).
- **Inferido:** interpretación razonable con justificación explícita, nunca presentada como hecho.
- **Propuesto:** mejora o regla sugerida, separada de las observaciones y a la espera de aprobación.
- **Pendiente:** pregunta sin resolver que requiere decisión humana.

## Incertidumbres

- Registrar en `reports/uncertainties.md` cada duda concreta: qué se observó, por qué es ambiguo y qué decisión se necesita.
- No resolver ambigüedades por cuenta propia: valor faltante, medida contradictoria o comportamiento no determinable quedan como Pendiente.
- Priorizar las dudas por impacto en la generación: las que bloquean un componente van primero.

## Qué no hacer

- No ejecutar el lote ni sus dependencias.
- No modificar la exportación original.
- No fusionar ni reescribir componentes en esta etapa: el análisis describe, no transforma.
- No proponer rediseños: las propuestas se limitan a fidelidad, reutilización y corrección.

## Criterio de salida

- Cada componente del lote aparece en el mapa con relaciones, props, estados y variantes.
- Los tokens observados están listados con valores exactos y procedencia.
- Toda afirmación lleva clasificación; toda duda está en `uncertainties.md`.

## Salidas

- `reports/ANALYSIS.md`: análisis por componente, tokens, duplicaciones aparentes, accesibilidad y limitaciones, con hallazgos clasificados.
- `reports/COMPONENT-MAP.md`: mapa de componentes, relaciones y jerarquía.
- `reports/uncertainties.md`: preguntas concretas priorizadas para el humano.
- `inventory.json` actualizado con hallazgos del análisis cuando corresponda.
