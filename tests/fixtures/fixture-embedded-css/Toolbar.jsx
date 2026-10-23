import React from "react";
import "./toolbar.css";

export function Toolbar({ onAction }) {
  return (
    <div className="toolbar">
      <button type="button" className="toolbar__btn" onClick={onAction}>
        Acción
      </button>
    </div>
  );
}

/* toolbar.css */
.toolbar {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: #1d2939;
  border-radius: 6px;
}

.toolbar__btn {
  padding: 6px 12px;
  border: 0;
  border-radius: 4px;
  background: #2f6feb;
  color: #ffffff;
  cursor: pointer;
}
