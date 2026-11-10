import type { ReactNode } from "react";
import styles from "./Card.module.css";

type CardProps = {
  title?: string;
  children: ReactNode;
};

// 共通のカード。見出し（title）は省略できる
export function Card({ title, children }: CardProps) {
  return (
    <section className={styles.card}>
      {title && <h2 className={styles.title}>{title}</h2>}
      {children}
    </section>
  );
}
