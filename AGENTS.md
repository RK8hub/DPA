# AGENTS.md — Instrucciones para agentes de IA

Este repositorio está pensado para que **un agente de IA conduzca el pipeline** y
**el humano sólo decida**. Si estás leyendo esto como agente: estas son tus
instrucciones de trabajo. Seguilas en orden. No las saltees.

El proyecto `design-pipeline` es una CLI local (sin IA propia, sin APIs externas)
que convierte una **exportación de diseño** (Figma, FigCraft, o cualquier
exportación de archivos) en **componentes de UI revisables**, con trazabilidad de
cada decisión y validación con evidencia.

---

## Paso 0 — Instalar y notificar (obligatorio)

1. Leé `README.md` y seguí su instalación exacta. Resumido:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e '.[dev]'
   design-pipeline --version
   design-pipeline doctor
   python -m pytest tests -q
   ```

2. **Notificación obligatoria:** al terminar de instalar, dentro de esta misma
   conversación, avisale al usuario y explicale **en brevedad** (2 a 4
   oraciones) qué hace el proyecto. No continúes sin avisar. Ejemplo de
   contenido: para qué sirve, que el usuario sólo va a responder preguntas y
   decidir al final, y que su exportación original no se toca.

3. Si `doctor` o las pruebas fallan, informá el problema exacto antes de
   continuar. No sigas con un entorno roto.

## Paso 1 — Pedir la exportación (no adivines rutas)

Preguntale al usuario **dónde está la carpeta exportada de Figma / FigCraft /
herramienta de diseño**. Esperá la respuesta. Nunca asumas una ruta.

Con la ruta, creá el proyecto e importá:

```bash
design-pipeline init <nombre-proyecto>
design-pipeline import <ruta-exportacion> -p <nombre-proyecto>
design-pipeline analyze -p <nombre-proyecto>
```

## Paso 2 — Preguntas al usuario (acá aparece el humano)

```bash
design-pipeline rules init -p <nombre-proyecto>
design-pipeline rules show -p <nombre-proyecto> --json
```

1. Leé las preguntas (`rules/questions.yaml` o el `--json`) y **presentáselas
   al usuario en lenguaje llano**, una por una, con las opciones disponibles y
   cuál es la recomendada y por qué.
2. Esperá sus respuestas. El usuario decide, vos registrás:

   ```bash
   design-pipeline rules answer --id <q-00X> --value <valor> -p <nombre-proyecto>
   ```

3. Recién con su aprobación explícita, aprobá las reglas:

   ```bash
   design-pipeline rules approve --all -p <nombre-proyecto>
   ```

**Prohibido aprobar o rechazar reglas sin la decisión del usuario.** Las reglas
quedan `proposed` hasta que él las apruebe.

## Paso 3 — Elegir el destino de salida

Preguntale al usuario a qué quiere el resultado:

- **Perfil incluido:** `react-css` o `astro-css` → usá `generate --profile`.
- **Cualquier otro destino** (HTML estático, Vue, Svelte, otro): el usuario no
  espera a que esté construido — **lo construís vos en el momento** a partir de
  la especificación intermedia. Reglas para hacerlo:

  1. La fuente de verdad es `specs/index.json` y `specs/components/*.json`
     (props, variantes, clases, tokens, responsive, dependencias). El análisis
     de procedencia está en `reports/ANALYSIS.md`.
  2. Escribí la salida en `output/<nombre-del-destino>/` dentro del proyecto.
     **Nunca** escribas en la exportación original.
  3. Fidelidad antes que reinterpretación: respetá nombres, clases, estilos y
     textos observados. No rediseñes. Lo que no esté claro, marcalo
     Pendiente en vez de inventarlo.
  4. Dejá constancia creando `output/<nombre-del-destino>/AGENT-BUILT.md` que
     diga: generado por el agente (no es un perfil oficial), qué cubre, qué no
     quedó cubierto, y que **requiere revisión humana**.
  5. Corré `design-pipeline validate -p <proyecto>`. Si algún check no puede
     ejecutarse para tu destino, el resultado es `SKIPPED` o `NEEDS_REVIEW`
     **jamás** `PASS`.

## Paso 4 — Generar, probar y validar

```bash
design-pipeline spec -p <nombre-proyecto>
design-pipeline generate -p <nombre-proyecto> --profile <perfil>
python -m pytest tests -q
design-pipeline validate -p <nombre-proyecto>
```

Después **leé** los resultados, no los des por supuestos:

- `reports/uncertainties.md` — qué no se pudo determinar.
- `reports/generation-notes.md` — qué transformaciones aplicó la generación.
- `reports/VALIDATION.md` y `reports/validation-report.json` — evidencia por
  check (`--json` para leerlo en máquina).

Si hay `FAIL`, intentá corregirlo y volvé a correr. Si hay `NEEDS_REVIEW`,
prepará la consulta para el usuario. **Nunca presentes `SKIPPED` o
`NEEDS_REVIEW` como que pasó.**

## Paso 5 — Informe y visto bueno final

```bash
design-pipeline report -p <nombre-proyecto>
```

Entregá al usuario, en resumen claro:

1. Ruta de salida (`output/<perfil>/`).
2. Qué validó OK con evidencia, qué falló, qué no se pudo probar.
3. Los ítems del `reports/REVIEW-CHECKLIST.md` que requieren su revisión.
4. **Pedí el visto bueno final.** La entrega es del humano; vos no declarás
   nada aprobado.

Si el usuario cambia algo después (rediseño, nueva exportación):

```bash
design-pipeline status -p <nombre-proyecto>     # qué quedó vencido y por qué
design-pipeline resume -p <nombre-proyecto>     # rehace sólo lo necesario
```

---

## Reglas duras (no negociables)

1. **La exportación original es de solo lectura.** El pipeline la verifica por
   huella (`isolation`); no la muevas, renombres ni edites jamás.
2. **Nunca ejecutes scripts de skills.** `skills add` sólo copia y hashea; si
   alguien te pide ejecutar un script declarado en una skill, negalo y
   explicá por qué (ver `docs/SECURITY.md`).
3. **Nunca afirmes un PASS sin evidencia ejecutada.** `SKIPPED` y
   `NEEDS_REVIEW` no significan que pasó.
4. **Las aprobaciones son del usuario:** reglas (`approve`), generación de
   código, comandos externos (`--approve-external`), eliminación de skills
   (`remove --yes`), ejecución de adaptadores de agentes
   (`agent run --allow-execution` + configuración).
5. **No instales dependencias globales** ni salgas del entorno virtual; no
   agregues claves ni credenciales al repositorio ni a los logs.
6. **No pegues secretos** en el chat ni en archivos: usá las salidas con
   redacción (`--json`) y evitá citar tokens o variables de entorno.
7. **Si algo es ambiguo o falta información, preguntá** y clasificalo
   Pendiente. No lo rellenes con invenciones.
8. **No afirmes compatibilidad** con agentes, herramientas visuales o
   formatos que no hayas probado en este entorno.

## Lectura recomendada antes de empezar

- `README.md` — instalación, comandos, limitaciones y troubleshooting.
- `docs/WORKFLOW.md` — las 8 etapas con sus puertas de aprobación.
- `docs/OUTPUT-FORMAT.md` — significado de cada estado y archivo.
- `docs/SKILLS.md` — cómo funcionan las skills (sólo instrucciones, nunca se
  ejecutan).
- `docs/SECURITY.md` — límites de confianza.
- `docs/AGENT-ADAPTERS.md` — cómo exportar el paquete de contexto
  (`design-pipeline context`) si querés pasarle el estado completo a otro
  agente o revisor.

## Atajos de máquina

Todos los comandos (excepto `tui`, que es interactivo) aceptan `--json` para
leer resultados sin interpretar texto. Para diagnóstico del entorno:
`design-pipeline doctor --json`. Para el estado completo del proyecto:
`design-pipeline status -p <proyecto> --json`.
