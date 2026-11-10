import type { User } from "firebase/auth";
import {
  getCurrentFirebaseUser,
  logoutFromFirebase,
} from "@/lib/firebase/auth";

export class UnauthenticatedRequestError extends Error {
  constructor() {
    super("Firebaseのログイン情報を確認できませんでした。");
    this.name = "UnauthenticatedRequestError";
  }
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  firebaseUser: Pick<User, "getIdToken"> | null = getCurrentFirebaseUser(),
) {
  if (!firebaseUser) {
    throw new UnauthenticatedRequestError();
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await firebaseUser.getIdToken()}`);

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    await logoutFromFirebase().catch(() => undefined);
  }

  return response;
}
