import React from "react";
import { Button } from "../Button/Button";
import logo from "../../assets/logo.svg";
import "./Card.css";

export interface CardProps {
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
  children?: React.ReactNode;
}

export function Card({ title, subtitle, actionLabel, onAction, children }: CardProps) {
  return (
    <article className="card">
      <header className="card__header">
        <img className="card__logo" src={logo} />
        <div className="card__heading">
          <h2 className="card__title">{title}</h2>
          {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
        </div>
      </header>
      <div className="card__body">{children}</div>
      {actionLabel ? (
        <footer className="card__footer">
          <Button variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        </footer>
      ) : null}
    </article>
  );
}
