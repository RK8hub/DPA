import React from "react";
import "./panel.css";

export function Panel({ title = "Panel", variant = "default" }) {
  return (
    <section className={`panel panel--${variant}`}>
      <h2 className="panel__title">{title}</h2>
      <div className="panel__body" />
    </section>
  );
}

/* panel.css */
.panel {
  padding: 16px;
  border-radius: 8px;
  background: #101828;
  color: #f9fafb;
}

.panel--accent {
  border-left: 3px solid #2f6feb;
}

.panel__title {
  margin: 0 0 8px;
  font-size: 18px;
  color: #e4e7ec;
}

.panel__body {
  font-size: 14px;
  color: #98a2b3;
}
