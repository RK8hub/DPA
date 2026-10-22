# Trazabilidad

Cada pieza de información que produce el pipeline debe poder rastrearse hasta su origen y su estado de confianza. La trazabilidad permite auditar decisiones, detectar obsolescencia y reanudar ejecuciones sin perder contexto.

## Procedencia de hallazgos

- Cada hallazgo del análisis registra: archivo de origen, línea cuando sea posible, y su clasificación:
  - **Observado:** respaldado directamente por el contenido de un archivo.
  - **Inferido:** interpretación razonable, siempre con justificación explícita.
  - **Propuesto:** cambio o regla sugerida, aún no aprobada.
  - **Pendiente:** pregunta sin resolver, con la duda concreta formulada.
- Un hallazgo sin procedencia no entra en `reports/ANALYSIS.md` ni en `reports/COMPONENT-MAP.md`.
- Las inferencias deben poder separarse de las observaciones al leer el informe: etiqueta o sección consistente en todas las salidas.

## Decisiones

- Cada decisión registrada en `reports/DECISIONS.md` incluye:
  - qué se decidió (objeto: regla, componente, valor, dependencia);
  - quién decidió (humano identificado o "agente bajo regla aprobada");
  - cuándo (fecha y ejecución de referencia);
  - cómo (respuesta a pregunta de descubrimiento, archivo de reglas, o aprobación explícita);
  - procedencia (hallazgo o pregunta que la originó).
- Las reglas de `rules/design-rules.yaml` conservan estado (propuesta, aprobada, rechazada) y el enlace a la decisión que las aprobó.
- Una regla sin decisión asociada no se considera vigente.

## Validaciones

- Cada resultado de validación en `reports/VALIDATION.md` registra:
  - comando o comprobación ejecutada;
  - código de salida o resultado;
  - versión de la herramienta cuando aplique;
  - limitaciones (por qué no se pudo ejecutar algo);
  - evidencia asociada (ruta de artefacto, salida capturada).
- Nunca se escribe PASS sin ejecución registrada. Si no corrió, el estado es SKIPPED o NEEDS_REVIEW con el motivo.

## Logs y estado

- Cada ejecución genera logs estructurados en JSONL, con identificador de ejecución, etapa, evento y timestamp.
- El estado por proyecto guarda hashes de las entradas (archivos de la exportación, reglas, configuración, skills activas). Si los hashes cambian, se identifican las etapas potencialmente obsoletas antes de reanudar.
- Los artefactos generados quedan asociados a la ejecución que los produjo; no se sobrescriben resultados anteriores sin permiso.

## Criterio de salida

- Es posible reconstruir, para cualquier componente generado, su cadena completa: archivo de origen, hallazgo, especificación, regla aplicada y validación.
- Ninguna afirmación de las salidas carece de procedencia ni de estado de confianza.
