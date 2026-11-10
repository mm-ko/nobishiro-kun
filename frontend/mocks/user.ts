// ① ログイン中ユーザー（UI-001・UI-002）
// すべてダミー。実在のメールアドレス・本物のFirebaseの値は入れない。
import type { UserResponse } from "@/types/api";

/** Firebase側のユーザー情報（ダミー） */
export type MockAuthUser = { email: string };

export const mockAuthUser: MockAuthUser = {
  email: "sample-parent@example.com",
};

/** BEのユーザー情報（API設計書 3.1 の形） */
export const mockUser: UserResponse = {
  id: "1",
  created_at: "2026-09-26T03:00:00Z",
};
