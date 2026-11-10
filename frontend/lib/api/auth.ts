import type { User } from "firebase/auth";
import type { UserResponse } from "@/types/api";
import { authenticatedFetch } from "./client";

type InitializedUser = {
  firebaseUid: string;
  user: UserResponse;
};

let initializedUser: InitializedUser | null = null;
let initializingUser: {
  firebaseUid: string;
  request: Promise<UserResponse>;
} | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isUserResponse(value: unknown): value is UserResponse {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.created_at === "string"
  );
}

async function putMyUser(firebaseUser: User): Promise<UserResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new Error("APIの接続先が設定されていません。");
  }

  const response = await authenticatedFetch(
    `${apiBaseUrl}/v1/users/me`,
    { method: "PUT" },
    firebaseUser,
  );
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok || !isUserResponse(payload)) {
    throw new Error("ユーザー情報の初期登録に失敗しました。");
  }

  return payload;
}

export async function initializeMyUser(
  firebaseUser: User,
): Promise<UserResponse> {
  if (initializedUser?.firebaseUid === firebaseUser.uid) {
    return initializedUser.user;
  }

  if (initializingUser?.firebaseUid === firebaseUser.uid) {
    return initializingUser.request;
  }

  const request = putMyUser(firebaseUser);
  initializingUser = { firebaseUid: firebaseUser.uid, request };

  try {
    const user = await request;
    if (initializingUser?.request === request) {
      initializedUser = { firebaseUid: firebaseUser.uid, user };
    }
    return user;
  } finally {
    if (initializingUser?.request === request) {
      initializingUser = null;
    }
  }
}

export function clearInitializedMyUser() {
  initializedUser = null;
  initializingUser = null;
}
