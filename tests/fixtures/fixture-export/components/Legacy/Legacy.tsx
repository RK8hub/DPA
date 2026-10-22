import React from "react";
import "./old-styles.css";

// Componente legado exportado sin su hoja de estilos correspondiente.
export function Legacy({ title }: { title: string }) {
  return <section className="legacy">{title}</section>;
}
