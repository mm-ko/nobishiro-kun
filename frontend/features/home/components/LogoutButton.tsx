"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { useAuth } from "@/features/auth/context/AuthContext";

// ログアウトのボタン。押すとログイン状態を解除し、/login へ移動する。
// router.replace を使うことで、ログアウト後に「戻る」でホームへ戻れないようにしている。
export function LogoutButton() {
  const router = useRouter();
  const { isLoading, logout } = useAuth();

  async function handleLogout() {
    try {
      await logout();
      router.replace("/login");
    } catch {
      // Firebase上でログアウトできなかった場合は、認証済み画面に留める。
    }
  }

  return (
    <Button variant="secondary" onClick={handleLogout} disabled={isLoading}>
      {isLoading ? "処理中..." : "ログアウト"}
    </Button>
  );
}
