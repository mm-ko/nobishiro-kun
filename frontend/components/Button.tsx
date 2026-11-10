import type { ComponentProps } from "react";
import styles from "./Button.module.css";

type ButtonProps = ComponentProps<"button"> & {
  // primary：画面の主な操作（1画面に1つ）／secondary：それ以外の操作
  variant?: "primary" | "secondary";
};

// 共通のボタン。通信中の二重送信を防ぐときは、使う側で disabled を渡す
export function Button({
  variant = "primary",
  type = "button",
  className,
  ...props
}: ButtonProps) {
  const classNames = [styles.button, styles[variant], className]
    .filter(Boolean)
    .join(" ");

  return <button type={type} className={classNames} {...props} />;
}
