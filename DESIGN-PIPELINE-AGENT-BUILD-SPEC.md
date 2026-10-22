# Especificación de construcción: Design Pipeline para agentes de IA

> **Instrucción principal para el agente constructor:** construí este proyecto en el repositorio y entorno de trabajo actuales. No te limites a describir una arquitectura ni a devolver fragmentos de ejemplo: inspeccioná el entorno, implementá el sistema, ejecutá las pruebas disponibles y documentá qué funciona y qué queda pendiente. Antes de tomar decisiones destructivas o instalar dependencias globales, pedí autorización. Si una decisión menor no está especificada, elegí una opción sencilla, segura y documentala.

## 1. Objetivo

Crear una herramienta local, orientada a terminal, que orqueste un flujo de trabajo de ingeniería de interfaces asistido por el LLM que el usuario ya utiliza desde una CLI o terminal.

El sistema **no debe requerir un modelo de IA propio ni una API de un proveedor por defecto**. Debe preparar el contexto de trabajo, cargar instrucciones y skills compatibles, coordinar scripts, registrar decisiones y producir componentes listos para revisión.

El flujo inicial está enfocado en lotes de componentes exportados de herramientas de diseño como Figcraft o Figma —por ejemplo JSX/TSX, CSS, SVG, imágenes, fuentes y archivos auxiliares—, pero el núcleo debe ser extensible a otros formatos y destinos.

El agente constructor debe crear una implementación funcional y modular, no una demostración de interfaz.

## 2. Principios obligatorios

1. **Fidelidad antes que reinterpretación:** conservar la intención visual y funcional del diseño de origen. No inventar rediseños ni cambiar estilos sin una regla explícita o aprobación.
2. **Humano en el circuito:** las decisiones ambiguas, las reglas de diseño nuevas y las modificaciones de alto impacto requieren aprobación configurable.
3. **Trazabilidad:** diferenciar claramente observaciones, inferencias, propuestas, decisiones aprobadas y resultados verificados.
4. **Reanudabilidad:** una ejecución interrumpida debe poder reanudarse sin repetir innecesariamente etapas ya completadas.
5. **Idempotencia:** volver a ejecutar una etapa no debe corromper ni duplicar los artefactos.
6. **Aislamiento:** nunca modificar la exportación original. Generar resultados en un directorio de trabajo y salida separado.
7. **Validación basada en evidencia:** no afirmar que una prueba pasó si no se ejecutó y registró su resultado.
8. **Independencia del proveedor:** separar el motor del flujo de los adaptadores específicos de cada agente o CLI.
9. **Extensibilidad:** admitir skills propias, skills externas y herramientas adicionales mediante un mecanismo de plugins documentado.
10. **Seguridad por defecto:** inspeccionar las skills externas antes de habilitarlas; no ejecutar scripts desconocidos automáticamente; no exponer secretos en logs.
11. **Portabilidad:** priorizar Linux y Python moderno; evitar depender de servicios alojados para las funciones centrales.
12. **Salidas legibles:** preferir Markdown, JSON y YAML para especificaciones, decisiones e informes.

## 3. Experiencia esperada

El usuario instala o clona el repositorio, ejecuta las instrucciones del README con su agente de terminal y configura el sistema local. La instalación debe crear un comando de proyecto —por ejemplo `design-pipeline`—, preferentemente mediante un entorno virtual y un entry point de Python. No instalar globalmente sin permiso.

Ejemplo de interfaz prevista:

```bash
design-pipeline init
design-pipeline doctor
design-pipeline import ./figcraft-export --project dashboard-operadores
design-pipeline analyze --project dashboard-operadores
design-pipeline review --project dashboard-operadores
design-pipeline generate --project dashboard-operadores --target astro-tailwind
design-pipeline validate --project dashboard-operadores
design-pipeline status --project dashboard-operadores
design-pipeline skills list
design-pipeline skills inspect ponytail
design-pipeline skills add ./my-skill
design-pipeline skills enable ponytail
```

Los comandos son una propuesta de interfaz: implementá un conjunto coherente y documentá la sintaxis definitiva. Debe existir un modo interactivo de terminal (TUI) y un modo no interactivo apropiado para automatización. Si el entorno no permite una TUI completa, el modo de texto interactivo debe seguir funcionando.

## 4. Flujo de trabajo por etapas

Implementá el pipeline como una máquina de estados explícita. Cada etapa debe declarar entradas, salidas, validaciones, estado y condiciones de aprobación.

### Etapa A — Inicialización

- Verificar versión de Python y dependencias necesarias.
- Crear un workspace local por proyecto.
- Crear configuración inicial y un identificador de ejecución.
- Detectar herramientas disponibles sin asumir que una CLI específica está instalada.
- Mostrar al usuario las dependencias ausentes y las acciones recomendadas.
- No modificar configuraciones globales de agentes sin aprobación.

### Etapa B — Importación e inventario

Aceptar una ruta de entrada que contenga archivos exportados. Crear un inventario de rutas, tipos, tamaños, hashes, referencias entre archivos y posibles recursos duplicados.

- Admitir inicialmente JSX/TSX, JS/TS, CSS, JSON, SVG, imágenes y Markdown.
- Conservar la estructura original en una zona de solo lectura lógica.
- Excluir de forma predeterminada `.git`, `node_modules`, `dist`, cachés, secretos y archivos grandes no pertinentes; permitir ajustar exclusiones.
- No ejecutar archivos de entrada.
- Detectar referencias rotas y archivos que no se pudieron analizar.
- Producir `inventory.json` y `IMPORT-REPORT.md`.

### Etapa C — Análisis del lote

Preparar un paquete de contexto para el agente, evitando enviar indiscriminadamente archivos binarios o contenido innecesario.

Analizar:

- componentes y sus relaciones;
- propiedades, estados y variantes;
- estilos, medidas, tipografías, colores y espaciados;
- recursos e imports;
- patrones compartidos y candidatos a reutilización;
- duplicaciones aparentes;
- problemas de accesibilidad y semántica;
- limitaciones de la exportación;
- incertidumbres que necesitan decisión humana.

Separar en la salida:
- **Observado:** directamente respaldado por los archivos.
- **Inferido:** interpretación razonable, con justificación.
- **Propuesto:** cambio o regla sugerida.
- **Pendiente:** pregunta no resuelta.

No deducir que dos componentes son intercambiables solo porque se parecen. Evaluar diferencias de comportamiento, propiedades y estados.

Entregables mínimos: `ANALYSIS.md`, `COMPONENT-MAP.md`, `uncertainties.md` e inventario actualizado.

### Etapa D — Reglas de diseño y preguntas

Ofrecer dos modos:

**Modo guiado:** el usuario proporciona reglas al inicio (framework, convenciones, límites, diseño responsive, tokens, accesibilidad y preferencias de reutilización).

**Modo descubrimiento:** el agente analiza el lote y formula preguntas para construir reglas específicas del proyecto.

Las preguntas deben ser concretas, agrupadas y priorizadas. Siempre que sea útil, ofrecer opciones y una recomendación explicada. Permitir respuestas parciales y registrar lo que siga pendiente.

Generar reglas propuestas y pedir aprobación antes de marcarlas como aprobadas. No modificar los principios centrales del sistema al crear reglas de proyecto.

Entregables: `DESIGN-RULES.md`, `DECISIONS.md` y `design-rules.yaml`, con estado y procedencia de cada regla.

### Etapa E — Especificación intermedia

Generar una representación independiente del framework que describa:

- identidad y propósito del componente;
- props, defaults, estados y variantes;
- jerarquía estructural;
- tokens usados;
- dependencias y recursos;
- reglas responsive;
- interacciones y accesibilidad;
- restricciones de fidelidad;
- relaciones con otros componentes;
- decisiones aprobadas y dudas abiertas.

Usar Markdown para lectura humana y JSON/YAML validado por esquemas para el procesamiento automático. La generación de Astro o React no debe exigir volver a analizar todo el lote si la especificación sigue vigente.

### Etapa F — Generación

Permitir perfiles de destino, como mínimo:
- Astro + CSS/Tailwind.
- React/JSX o TSX + CSS/Tailwind.

Diseñar el sistema para añadir destinos futuros sin acoplarlos al núcleo.

- Generar cada componente en su carpeta o convención definida por el perfil.
- Preservar nombres y props siempre que sea razonable.
- Evitar estilos globales involuntarios, imports rotos, nombres inconsistentes y duplicación innecesaria.
- No instalar dependencias automáticamente sin mostrar la propuesta y obtener permiso.
- Mantener la exportación original intacta.
- Registrar los cambios y decisiones relevantes.
- Crear un `README.md` por componente o grupo cuando ayude a explicar uso, props, variantes y limitaciones.

### Etapa G — Validación

Combinar validadores deterministas con pruebas que el agente genere para el lote actual. Las pruebas generadas no se consideran aprobadas por el simple hecho de existir.

Validaciones iniciales:
- integridad de archivos y estructura;
- validez de JSON/YAML y cumplimiento de esquemas;
- existencia de imports y recursos referenciados;
- lint, type-check y build cuando el proyecto de destino lo permita;
- pruebas funcionales cuando haya comportamiento verificable;
- pruebas responsive en viewports configurables;
- pruebas de accesibilidad automatizables;
- capturas y comparación visual cuando existan herramientas y referencias disponibles.

El sistema debe diferenciar `PASS`, `FAIL`, `SKIPPED` y `NEEDS_REVIEW`. Registrar comandos ejecutados, códigos de salida, versiones, limitaciones y evidencias. Nunca marcar como aprobado un test que no se ejecutó.

Si una herramienta necesaria no está instalada, informar el requisito y continuar con las comprobaciones restantes cuando sea seguro.

### Etapa H — Revisión y entrega

Mostrar un resumen legible y la ruta absoluta o relativa de la carpeta de salida. Incluir:
- componentes generados;
- archivos de explicación;
- reglas y decisiones aplicadas;
- pruebas ejecutadas y resultado;
- pruebas omitidas y motivo;
- advertencias y limitaciones;
- lista de revisión humana;
- diferencias relevantes respecto a la fuente.

La salida debe quedar aislada del código original y ser fácil de copiar al proyecto real una vez aprobada.

## 5. Sistema de skills y plugins

Implementar un registro de skills extensible. El usuario debe poder incorporar skills externas como plugins, por ejemplo una skill llamada `ponytail`, si dispone de ella. **No asumir qué hace Ponytail ni inventar su URL, repositorio o contrato**: tratarla como un nombre de ejemplo y permitir importar una skill desde una ruta local o una fuente explícitamente indicada por el usuario.

### Requisitos del sistema de skills

- Detectar skills internas y externas.
- Admitir al menos carpetas que contengan `SKILL.md` y recursos opcionales.
- Registrar nombre, descripción, versión si existe, origen, permisos requeridos, herramientas que invoca y etapas en las que puede participar.
- Comandos para listar, inspeccionar, validar, añadir, habilitar, deshabilitar y quitar una skill.
- Permitir importar desde una carpeta local; la instalación desde repositorios remotos debe requerir una URL explícita y confirmación.
- Mantener metadatos de procedencia y un hash de los archivos importados.
- No sobrescribir skills existentes silenciosamente.
- Verificar que `SKILL.md` tenga metadatos válidos cuando corresponda y contenido legible.
- Mostrar los scripts incluidos y sus permisos antes de habilitar la skill.
- No ejecutar scripts de una skill recién importada automáticamente.
- Permitir que una skill declare si es solo instructiva o si requiere ejecución de herramientas.
- Resolver conflictos entre instrucciones: los principios centrales y controles de seguridad prevalecen sobre las skills externas; las reglas aprobadas del proyecto prevalecen sobre recomendaciones genéricas de una skill.
- Registrar qué skills se activaron en cada ejecución y por qué.
- Permitir configurar skills por proyecto sin alterar la configuración global.
- Crear una interfaz de adaptadores para diferentes formatos de skills/agentes, sin asumir que todos usan el mismo estándar.

### Aislamiento y seguridad de plugins

Tratar instrucciones y recursos externos como contenido no confiable. Inspeccionar rutas, evitar traversal de directorios, no permitir que una skill sobrescriba archivos fuera de las rutas autorizadas y evitar mostrar secretos en logs. La herramienta debe pedir aprobación antes de ejecutar código externo o hacer cambios globales.

No prometer aislamiento de sandbox si no se implementa realmente. Documentar los límites de seguridad del agente y del sistema operativo.

## 6. Adaptadores de agentes

Crear una interfaz común para interactuar con agentes de terminal. No asumir que todos aceptan las mismas opciones de CLI ni que cargan las skills del mismo modo.

Cada adaptador debe declarar:
- comando ejecutable detectado;
- método para pasar el prompt/contexto;
- soporte de skills o instrucciones;
- modo interactivo y no interactivo;
- capacidades disponibles y limitaciones;
- cómo capturar el resultado sin filtrar secretos.

Implementar primero el mecanismo más sencillo que el entorno actual permita y dejar documentada la interfaz para añadir otros agentes. Si no hay una CLI compatible, permitir exportar un paquete de contexto/instrucciones que el usuario pueda cargar manualmente.

El núcleo debe funcionar sin agente para inventariar archivos, validar manifiestos y revisar el estado del proyecto.

## 7. Interfaz de terminal

Crear una TUI clara con:
- selección de proyecto y carpeta de entrada;
- elección entre modo guiado y descubrimiento;
- progreso y estado de cada etapa;
- preguntas con opciones, texto libre y posibilidad de posponer;
- revisión de reglas propuestas;
- selección de skills habilitadas;
- elección del perfil de destino;
- aprobación antes de generación o ejecución de código;
- resumen final y ruta de salida.

Si se usa una biblioteca TUI, elegir una mantenida y documentar la dependencia. Mantener también comandos CLI no interactivos para scripting y automatización. Evitar que la TUI contenga lógica de negocio: debe llamar al mismo motor que los comandos.

## 8. Estado, logs y recuperación

Cada proyecto debe tener un archivo de estado legible por máquina con:
- etapa actual;
- estado de cada etapa;
- entradas y hashes relevantes;
- versiones de configuración y skills;
- decisiones pendientes;
- artefactos generados;
- último resultado de validación;
- fecha y duración de cada ejecución.

Registrar logs estructurados en JSONL y un resumen humano en Markdown. No registrar tokens, contraseñas ni variables de entorno secretas.

Implementar comandos de estado y reanudación. Si cambian archivos de entrada, reglas o skills, identificar qué etapas podrían quedar obsoletas y solicitar o aplicar una repetición segura. No eliminar resultados anteriores sin permiso; conservar un historial por ejecución cuando sea viable.

## 9. Estructura sugerida del repositorio

Adaptá esta estructura si el entorno existente ya tiene una convención mejor, pero mantené las responsabilidades separadas.

```text
design-pipeline/
├── README.md
├── pyproject.toml
├── LICENSE
├── config/
│   ├── defaults.yaml
│   └── profiles/
├── principles/
│   ├── fidelity.md
│   ├── safety.md
│   ├── traceability.md
│   └── human-review.md
├── skills/
│   ├── inspect-design/SKILL.md
│   ├── analyze-batch/SKILL.md
│   ├── define-design-rules/SKILL.md
│   ├── generate-components/SKILL.md
│   └── validate-output/SKILL.md
├── src/
│   └── design_pipeline/
│       ├── cli.py
│       ├── tui/
│       ├── engine/
│       ├── adapters/
│       ├── skills/
│       ├── importers/
│       ├── validators/
│       ├── reporting/
│       └── workspace/
├── schemas/
├── templates/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── workspace/
    └── .gitkeep
```

No es necesario crear carpetas vacías sin uso. La configuración local y los datos generados deben estar fuera de los módulos de código cuando sea apropiado, y los artefactos de usuario no deben añadirse accidentalmente al repositorio.

## 10. Requisitos técnicos iniciales

- Priorizar Python 3.11+ salvo que el entorno requiera una versión diferente.
- Usar `pyproject.toml` y un entry point ejecutable.
- Elegir dependencias pequeñas y mantenidas.
- Usar validación tipada para los manifiestos.
- Separar IO, lógica de negocio, UI, adaptadores y validadores.
- Escribir pruebas unitarias para el motor de estados, resolución de reglas, importación segura y registro de skills.
- Escribir pruebas de integración con fixtures de exportaciones pequeñas.
- No exigir conexión a internet para las funciones locales básicas.
- No incorporar claves ni credenciales al repositorio.
- No introducir dependencias o servicios innecesarios.

Elegí las bibliotecas concretas tras inspeccionar el entorno y explicá la elección en la documentación técnica.

## 11. Documentación requerida

Crear y mantener:
- `README.md`: propósito, instalación, requisitos, primeros pasos, comandos, ejemplos, limitaciones y solución de problemas.
- `docs/ARCHITECTURE.md`: módulos, responsabilidades y flujo de datos.
- `docs/WORKFLOW.md`: etapas, entradas, salidas y puertas de aprobación.
- `docs/SKILLS.md`: formato, importación, validación, permisos y precedencia de skills.
- `docs/AGENT-ADAPTERS.md`: cómo incorporar otra CLI.
- `docs/CONFIGURATION.md`: configuración global y por proyecto.
- `docs/SECURITY.md`: límites de confianza, ejecución de scripts y manejo de secretos.
- `docs/OUTPUT-FORMAT.md`: estructura de salida y significado de estados.
- plantillas para `ANALYSIS.md`, `DESIGN-RULES.md`, `DECISIONS.md`, `VALIDATION.md` y `REVIEW-CHECKLIST.md`.

Documentar explícitamente las funciones que estén simuladas, incompletas o dependan de una herramienta externa.

## 12. Criterios de aceptación

El proyecto no se considera terminado hasta que se cumplan, o se documenten claramente como bloqueados, estos criterios:

1. Puede instalarse en un entorno de desarrollo limpio siguiendo el README.
2. El comando principal aparece y ofrece ayuda.
3. `doctor` identifica dependencias disponibles y ausentes.
4. Puede importar una carpeta de fixture sin modificar los archivos originales.
5. Genera un inventario y un informe de análisis.
6. Permite configurar reglas desde el inicio o iniciar un flujo de preguntas.
7. Guarda las respuestas y las decisiones en archivos persistentes.
8. Puede listar, inspeccionar e importar una skill externa desde una ruta local.
9. La skill externa no se ejecuta automáticamente durante la importación.
10. Puede seleccionar un perfil de salida y producir una estructura de componentes.
11. Ejecuta las validaciones disponibles y distingue `PASS`, `FAIL`, `SKIPPED` y `NEEDS_REVIEW`.
12. Produce un informe final con la ruta de salida y las pruebas realizadas.
13. Puede mostrar el estado y reanudar una ejecución interrumpida.
14. Las pruebas unitarias e integración pasan, o se documentan fallos reproducibles.
15. No afirma compatibilidad con agentes, herramientas visuales o skills que no hayan sido probados.

## 13. Orden de implementación

Trabajá por incrementos funcionales. No intentes implementar todo como un bloque monolítico.

1. Inspeccionar el repositorio y el entorno actuales. Si hay código existente, preservarlo y proponer cambios antes de reemplazarlo.
2. Definir el contrato del estado del proyecto, el manifiesto y las etapas.
3. Implementar CLI, configuración y workspace.
4. Implementar importación e inventario seguro.
5. Implementar el motor de estados, persistencia y logs.
6. Implementar el registro de skills y sus controles de seguridad.
7. Implementar análisis asistido por agente y el flujo de preguntas.
8. Implementar especificación intermedia y perfiles de generación.
9. Implementar validadores y reporte de resultados.
10. Implementar TUI.
11. Completar documentación, fixtures y pruebas.
12. Ejecutar pruebas, revisar seguridad y presentar un resumen final.

Después de cada incremento, ejecutar las pruebas pertinentes. No ocultar fallos ni reemplazar una funcionalidad real con un placeholder sin informarlo.

## 14. Informe final del agente constructor

Al terminar, devolver:
- resumen de lo implementado;
- decisiones técnicas relevantes y su justificación;
- archivos principales creados o modificados;
- comandos exactos de instalación y ejecución;
- pruebas ejecutadas y resultados reales;
- capacidades no implementadas y limitaciones;
- pasos manuales que el usuario todavía debe completar.

**Prioridad final:** construir una base pequeña, funcional, segura y extensible. Es preferible un flujo inicial que realmente importe, analice, registre decisiones y valide una exportación de ejemplo, antes que una arquitectura grande con muchas etapas que solo aparenten funcionar.
