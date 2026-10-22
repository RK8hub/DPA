import React, { useState } from "react";
import "./Stat.css";

export interface StatProps {
  label: string;
  value: number;
  unit?: string;
  decimals?: number;
}

export function Stat({ label, value, unit, decimals = 0 }: StatProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="stat" onClick={() => setExpanded(!expanded)}>
      <span className="stat__label">{label}</span>
      <strong className="stat__value">
        {value.toFixed(decimals)}
        {unit ? <span className="stat__unit">{unit}</span> : null}
      </strong>
      {expanded ? (
        <span className="stat__hint">Detalle no disponible en la exportación.</span>
      ) : null}
    </div>
  );
}
