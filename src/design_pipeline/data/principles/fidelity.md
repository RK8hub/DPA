# Fidelidad antes que reinterpretación

Principio rector: la exportación de origen define el resultado. El pipeline traduce el diseño a código; no lo rediseña, no lo interpreta ni lo "mejora". Toda desviación respecto de lo observado debe ser una decisión humana registrada, nunca una iniciativa del agente.

Este documento define reglas operativas para las etapas `analyze` (C), `spec` (E), `generate` (F) y `validate` (G).

## Reglas para la etapa C (Análisis)

- Registrar colores, tipografías, espaciados, medidas y valores de layout tal como aparecen en los archivos, con su procedencia (archivo y línea cuando sea posible).
- Clasificar cada hallazgo como Observado, Inferido, Propuesto o Pendiente. Una hipótesis sobre la intención del diseño es Inferido, nunca Observado.
- No deducir que dos componentes son intercambiables por parecerse: comparar props, estados, variantes y comportamiento antes de sugerir fusión o reutilización.
- No proponer mejoras de estilo, accesibilidad o rendimiento como si fueran parte del diseño de origen. Las mejoras válidas van como Propuesto, a la espera de una regla aprobada.
- Ante ambigüedades (valor faltante, medida contradictoria entre archivos, componente incompleto en la exportación), registrar la duda en `reports/uncertainties.md` con la pregunta concreta para el humano. No resolverla por cuenta propia.

## Reglas para la etapa E (Especificación)

- La especificación intermedia debe reflejar el diseño observado: props, defaults, estados, variantes, tokens, jerarquía estructural, reglas responsive e interacciones.
- Cada valor de la especificación debe poder rastrearse hasta un archivo de la exportación o hasta una regla aprobada. Sin origen ni regla, se marca como duda abierta.
- Documentar explícitamente las restricciones de fidelidad: qué no se debe tocar en la generación (colores, medidas críticas, textos).
- No incorporar decisiones de framework más allá de las necesarias: la especificación es independiente del destino.

## Reglas para la etapa F (Generación)

- Conservar nombres de componentes, props, estados y textos observados siempre que sea razonable. Cambiar un nombre solo con regla aprobada o imposibilidad técnica documentada.
- Reproducir colores, tipografías, espaciados y medidas desde la especificación, sin redondeos "por estética" ni normalizaciones no aprobadas.
- No aplicar estilos globales, resets ni mejoras de layout no pedidos. El CSS generado debe afectar solo al componente, salvo regla que diga lo contrario.
- En el perfil `astro-css`, convertir JSX a Astro solo cuando el componente sea estático (sin estado ni interactividad). Para componentes interactivos, generar una isla React con fallback explícito y documentado, preservando el mismo marcado y estilos.
- La conversión a Tailwind no está implementada de forma determinista: si el usuario la pide, informar la limitación y consultar antes de continuar.
- Ante un valor ambiguo o contradictorio entre archivos, marcar el componente o el atributo como NEEDS_REVIEW en el reporte de generación en lugar de elegir un valor.

## Reglas para la etapa G (Validación)

- La validación compara el resultado contra la especificación y los archivos de origen, no contra una noción estética de "mejor diseño".
- Diferencias de fidelidad detectadas (color distinto, medida alterada, tipografía no aplicada) se reportan como FAIL o NEEDS_REVIEW según corresponda, con evidencia: archivo, valor esperado, valor generado.
- Las capturas o comparaciones visuales solo se ejecutan si existen herramientas y referencias disponibles; si no, el resultado es SKIPPED, nunca PASS implícito.

## Criterio de salida

- Toda desviación respecto de la exportación está justificada por una regla aprobada o registrada como NEEDS_REVIEW/Pendiente.
- Ningún componente fue rediseñado, renombrado o "mejorado" sin decisión humana registrada en `reports/DECISIONS.md`.
