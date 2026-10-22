<!-- Plantilla de referencia para reports/ANALYSIS.md (etapa C) -->
<!-- Los archivos reales se generan desde los datos máquina (analysis.json) con
     analysis/reports.py:render_analysis(). Esta plantilla solo explica la
     estructura: no la edites ni la copies al workspace como informe real. -->

# Análisis del lote

- **Fecha:** {{created_at — timestamp ISO-8601 UTC}}
- **Huella del inventario:** {{inventory_fingerprint[:16]}}…
- **Componentes:** {{n componentes detectados}}
- **Hojas de estilo:** {{n hojas de estilo}}

> Cada hallazgo está clasificado como **Observado** (respaldado por los archivos),
> **Inferido** (interpretación con justificación), **Propuesto** (cambio
> sugerido, requiere aprobación) o **Pendiente** (pregunta sin resolver).

## Observado

- **[{{tipo — p. ej. componente, tokens, accesibilidad, estilos}}]** {{mensaje del hallazgo}}
  - Fuente: `{{ruta/archivo.ext}}` (con línea cuando está disponible)
  - Justificación: {{por qué se registra como observado}}

## Inferido

- **[{{tipo}}]** {{mensaje — nunca presentado como hecho}}
  - Fuente: `{{ruta/archivo.ext}}`
  - Justificación: {{interpretación explícita}}

## Propuesto

- **[{{tipo}}]** {{cambio o regla sugerida — espera aprobación humana}}
  - Fuente: `{{ruta/archivo.ext}}`
  - Justificación: {{motivo de la sugerencia}}

## Pendiente

- **[{{tipo}}]** {{pregunta sin resolver — requiere decisión humana}}
  - Fuente: `{{ruta/archivo.ext}}`
  - Justificación: {{por qué es ambiguo}}

<!-- Si una clase de hallazgos está vacía, el renderizador real escribe
     "- (sin hallazgos)" en su sección. -->

## Componentes

| Componente | Archivo | Props | Interactivo | Relaciones |
| --- | --- | --- | --- | --- |
| `{{nombre}}` | `{{ruta}}` | {{prop1, prop2}} o `—` | `sí` / `no` | {{otros componentes}} o `—` |

## Tokens detectados

| Token | Valor |
| --- | --- |
| `{{--nombre-custom-property}}` | `{{valor literal}}` |

<!-- Si no hay custom properties: "- Sin custom properties detectadas." -->

## Duplicaciones aparentes (requieren revisión)

- `{{ruta/a}}` ↔ `{{ruta/b}}`: {{n}}% de similitud textual. No se concluye que
  sean intercambiables.

<!-- Sección omitida por el renderizador cuando no hay duplicaciones. -->

## Limitaciones de la exportación

- {{archivos no analizables, exclusiones aplicadas, referencias rotas heredadas}}

<!-- Si no hay limitaciones: "- Ninguna detectada." -->

<!-- Notas de lectura:
     - Los conteos de esta cabecera también están en analysis.json y en el
       --json del comando analyze.
     - Los hallazgos Propuesto no se aplican solos: hay que convertirlos en
       regla (etapa rules) y aprobarla con `rules approve`.
     - Incertidumbres y opciones van en reports/uncertainties.md, no acá. -->
