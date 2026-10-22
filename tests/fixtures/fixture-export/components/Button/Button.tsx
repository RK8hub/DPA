import React from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export interface ButtonProps {
  /** Variante visual del botón. */
  variant?: ButtonVariant;
  /** Tamaño: sm o md. */
  size?: "sm" | "md";
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  onClick,
  children,
}: ButtonProps) {
  const classes = ["btn", `btn--${variant}`, `btn--${size}`]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} onClick={onClick} disabled={disabled} type="button">
      {children}
    </button>
  );
}
