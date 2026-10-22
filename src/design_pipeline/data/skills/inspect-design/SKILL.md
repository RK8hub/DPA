---
name: inspect-design
description: "Guía para inspeccionar una exportación de herramientas de diseño y alimentar el inventario sin ejecutar ni modificar los archivos de origen."
version: 1.0.0
format: markdown-folder
mode: instructive
permissions: [read-workspace, write-reports]
tools: []
stages: [import]
scripts: []
---

# Inspeccionar una exportación

Objetivo: recorrer la carpeta de origen de la etapa `import` y producir hallazgos accionables para `inventory.json` y el reporte de importación. Esta skill es solo instructiva: no ejecuta código ni modifica la exportación.

## Qué hacer

1. Recorrer la estructura de directorios y anotar agrupaciones naturales (por componente, por tipo de archivo, por fecha).
2. Clasificar archivos por tipo relevante: JSX/TSX, JS/TS, CSS, JSON, SVG, imágenes, fuentes y Markdown.
3. Detectar componentes: cada archivo JSX/TSX es un candidato; anotar nombre, ruta, props declaradas y si recibe otros componentes como hijos o imports.
4. Registrar assets: imágenes, fuentes y SVG, con ruta, tamaño y hash. Anotar qué componente los referencia.
5. Registrar dependencias: imports entre archivos de la exportación y referencias a paquetes externos leídas en los archivos. Solo lo que se lee, sin ejecutar nada.
6. Identificar posibles duplicados: archivos con hash idéntico o contenido muy similar. Anotarlos como candidatos, sin fusionar nada.
7. Detectar referencias rotas: imports o rutas que apuntan a archivos ausentes en la exportación.
8. Señalar exclusiones aplicadas (`.git`, `node_modules`, `dist`, cachés, archivos grandes) en el reporte, con el motivo.

## Qué no hacer

- No ejecutar ningún archivo de la exportación, ni instalar dependencias declaradas en ella.
- No modificar, renombrar ni mover archivos de origen: la exportación es de solo lectura.
- No salir de la carpeta de origen ni seguir symlinks que apunten fuera de ella.
- No analizar binarios más allá de tamaño y hash; no intentar abrirlos con herramientas del sistema.
- No resolver dudas de diseño por cuenta propia: van a `reports/uncertainties.md`.

## Cómo reportar hallazgos

- Cada hallazgo lleva: ruta relativa, tipo de dato (estructura, componente, asset, dependencia, duplicado, referencia rota) y clasificación: Observado para lo leído directamente, Inferido solo con justificación, Pendiente para lo que requiere consulta.
- Los duplicados se reportan como aparentes: la similaridad no implica intercambialidad.
- Las limitaciones (archivos no analizables, exclusiones) se enumeran explícitamente en el reporte de importación.
- Confirmar al final que el hash de los archivos de origen no cambió respecto del recorrido inicial.

## Criterio de salida

- `inventory.json` cubre rutas, tipos, tamaños, hashes, referencias entre archivos y duplicados candidatos.
- El reporte de importación resume estructura, componentes detectados, assets, dependencias, referencias rotas, exclusiones y limitaciones.
- Ninguna duda de diseño quedó resuelta sin registrar procedencia.

## Salidas

- `inventory.json` (actualizado): entradas con ruta, tipo, tamaño, hash, referencias y clasificación.
- `reports/IMPORT-REPORT.md`: resumen legible de la inspección, exclusiones y limitaciones.
- Entradas de `reports/uncertainties.md`: dudas detectadas durante la inspección, formuladas como preguntas concretas.
