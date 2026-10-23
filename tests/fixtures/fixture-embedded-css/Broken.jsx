import React from "react";
import "./broken.css";

export function Broken({ label = "sin estilos" }) {
  return <p className="broken">{label}</p>;
}

/* broken.css */
.broken {
  color: #ff0000;
  padding: 4px;
