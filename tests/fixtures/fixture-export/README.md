# Exportación de ejemplo (fixture)

Lote simulado de una exportación de herramienta de diseño para las pruebas de
integración de design-pipeline.

Contenido:

- `components/Button` — componente estático con variantes y props con defaults.
- `components/Card` — componente que importa Button y un asset SVG (con `img` sin `alt`, hallazgo de accesibilidad real).
- `components/Stat` — componente interactivo (`useState`, `onClick` en un `div`).
- `components/Legacy` — componente con una referencia rota deliberada (`./old-styles.css`).
- `styles/tokens.css` — tokens de diseño (`:root` con custom properties).
- `assets/logo.svg`, `assets/sparkline.svg` — recursos gráficos.
- `data/metrics.json` — datos de ejemplo.
