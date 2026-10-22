<!-- Plantilla de referencia para reports/REVIEW-CHECKLIST.md (etapa H) -->
<!-- Los archivos reales se generan desde reporting/summary.py:
     _render_checklist(), con los datos de validation-report.json,
     generation-notes.md, las reglas y state.decisions_pending. La completa y
     cierra una persona: es el cierre humano de la entrega. -->

# Checklist de revisión humana

Completá esta lista antes de copiar la salida al proyecto real.

## Revisión visual y de fidelidad

- [ ] Comparar cada componente generado con el diseño original (uno por uno).
- [ ] Verificar colores, tipografías, espaciados y medidas contra los tokens observados.
- [ ] Confirmar que no se introdujeron estilos, colores o componentes nuevos.
- [ ] Revisar comportamiento responsive en los breakpoints del export (p. ej. `@media (min-width: 768px)`).

## Revisión funcional

- [ ] Probar props y variantes de cada componente en el proyecto destino.

<!-- Solo cuando el perfil es astro-css, el renderizador agrega: -->
- [ ] Instalar y configurar `@astrojs/react` si hay islas (no instalado automáticamente).
- [ ] Verificar que las islas reciben `client:*` donde hace falta interactividad.

## Ítems pendientes registrados por el pipeline

<!-- Uno por cada ítem recolectado por _collect_needs_review(): -->
- [ ] [validación:{{id-del-check}}] {{detail del check en NEEDS_REVIEW}}
- [ ] [generación] {{ítem de la sección "Revisión humana pendiente" de generation-notes.md}}
- [ ] [reglas] {{r-001}} sigue propuesta (no aplicada): {{texto de la regla}}
- [ ] [decisiones] pregunta {{q-00X}} sin responder

<!-- Sin ítems: "- Ningún ítem pendiente registrado." -->

## Validación

<!-- Una línea por check de validation-report.json, en su orden. La casilla
     queda marcada cuando el estado es SKIPPED, NEEDS_REVIEW o FAIL (es decir,
     todo lo que no es un PASS ejecutado). El detail va truncado a 120
     caracteres en el archivo real. -->
- [x] `{{SKIPPED}}` — {{Build/lint del proyecto destino}}: {{motivo, truncado a 120 caracteres}}
- [x] `{{NEEDS_REVIEW}}` — {{Accesibilidad automatizable}}: {{hallazgos, truncado}}
- [ ] `{{PASS}}` — {{Integridad de archivos de salida}}: {{detalle, truncado}}

## Entrega

- [ ] Copiar `{{ruta/output/<perfil>}}` al proyecto destino (la fuente original quedó intacta).
- [ ] Ejecutar build/lint/tests del proyecto destino sobre los componentes copiados.
- [ ] Registrar en el proyecto destino qué reglas/procedencias se aplicaron.

<!-- Notas de lectura:
     - Este checklist no se genera si nunca corrió generate/validate: la etapa
       report falla con "No hay salida generada: ejecutá generate y validate
       primero."
     - La misma lista de ítems, con conteo, está en reports/DELIVERY.md
       ("Revisión humana pendiente (N)") y en el --json del comando report
       (needs_review_count).
     - El veredicto de la validación no se declara acá: está en
       reports/VALIDATION.md; un veredicto pass_with_review deja ítems con
       casilla marcada igual. -->
