import type { ComponentProps } from "react";
import styles from "./TextField.module.css";

type TextFieldProps = Omit<ComponentProps<"input">, "id"> & {
  // 見出し（label）と入力欄を結びつけるため、id は必ず渡す
  id: string;
  label: string;
  // エラー文の内容は、使う画面で決めて渡す
  error?: string;
};

// 見出し付きの共通の入力欄
export function TextField({
  id,
  label,
  error,
  className,
  ...props
}: TextFieldProps) {
  const errorId = `${id}-error`;
  const inputClassNames = [styles.input, error && styles.hasError, className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <input
        id={id}
        className={inputClassNames}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        {...props}
      />
      {error && (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
