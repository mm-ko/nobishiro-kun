import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { clearInitializedMyUser, initializeMyUser } from "@/lib/api/auth";
import {
  loginWithFirebase,
  logoutFromFirebase,
  observeFirebaseAuthState,
  registerWithFirebase,
} from "@/lib/firebase/auth";

vi.mock("@/lib/api/auth", () => ({
  clearInitializedMyUser: vi.fn(),
  initializeMyUser: vi.fn(),
}));

vi.mock("@/lib/firebase/auth", () => ({
  loginWithFirebase: vi.fn(),
  logoutFromFirebase: vi.fn(),
  observeFirebaseAuthState: vi.fn(),
  registerWithFirebase: vi.fn(),
}));

const clearInitializedMyUserMock = vi.mocked(clearInitializedMyUser);
const initializeMyUserMock = vi.mocked(initializeMyUser);
const loginWithFirebaseMock = vi.mocked(loginWithFirebase);
const logoutFromFirebaseMock = vi.mocked(logoutFromFirebase);
const observeFirebaseAuthStateMock = vi.mocked(observeFirebaseAuthState);
const registerWithFirebaseMock = vi.mocked(registerWithFirebase);

const firebaseUser = { uid: "firebase-user-1" } as never;
const currentUser = {
  id: "app-user-1",
  created_at: "2026-10-20T00:00:00Z",
};

function AuthStateProbe() {
  const { user, isLoading, login, register, logout } = useAuth();

  return (
    <>
      <span>{isLoading ? "loading" : "ready"}</span>
      <span>{user?.id ?? "guest"}</span>
      <button onClick={() => void login("test@example.com", "password")}>
        login
      </button>
      <button onClick={() => void register("test@example.com", "password")}>
        register
      </button>
      <button onClick={() => void logout()}>logout</button>
    </>
  );
}

describe("AuthProvider", () => {
  let onUserChanged: (user: typeof firebaseUser | null) => void;

  beforeEach(() => {
    clearInitializedMyUserMock.mockReset();
    initializeMyUserMock.mockReset();
    initializeMyUserMock.mockResolvedValue(currentUser);
    loginWithFirebaseMock.mockReset();
    loginWithFirebaseMock.mockResolvedValue(firebaseUser);
    registerWithFirebaseMock.mockReset();
    registerWithFirebaseMock.mockResolvedValue(firebaseUser);
    logoutFromFirebaseMock.mockReset();
    logoutFromFirebaseMock.mockResolvedValue(undefined);
    observeFirebaseAuthStateMock.mockReset();
    observeFirebaseAuthStateMock.mockImplementation((onChanged) => {
      onUserChanged = onChanged as typeof onUserChanged;
      return vi.fn();
    });
  });

  test("Firebaseの認証状態を復元するまでは読み込み中にする", async () => {
    render(
      <AuthProvider>
        <AuthStateProbe />
      </AuthProvider>,
    );

    expect(screen.getByText("loading")).toBeDefined();

    await act(async () => onUserChanged(firebaseUser));

    expect(await screen.findByText("app-user-1")).toBeDefined();
    expect(screen.getByText("ready")).toBeDefined();
    expect(initializeMyUserMock).toHaveBeenCalledWith(firebaseUser);
  });

  test("ログインと新規登録の後にアプリ内ユーザーを初期登録する", async () => {
    render(
      <AuthProvider>
        <AuthStateProbe />
      </AuthProvider>,
    );
    await act(async () => onUserChanged(null));

    fireEvent.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(loginWithFirebaseMock).toHaveBeenCalledOnce());
    expect(initializeMyUserMock).toHaveBeenLastCalledWith(firebaseUser);

    fireEvent.click(screen.getByRole("button", { name: "register" }));
    await waitFor(() =>
      expect(registerWithFirebaseMock).toHaveBeenCalledOnce(),
    );
    expect(initializeMyUserMock).toHaveBeenLastCalledWith(firebaseUser);
  });

  test("ログアウト時にFirebaseセッションと初期登録キャッシュを消す", async () => {
    render(
      <AuthProvider>
        <AuthStateProbe />
      </AuthProvider>,
    );
    await act(async () => onUserChanged(firebaseUser));

    fireEvent.click(screen.getByRole("button", { name: "logout" }));

    await waitFor(() => expect(logoutFromFirebaseMock).toHaveBeenCalledOnce());
    expect(clearInitializedMyUserMock).toHaveBeenCalled();
    expect(await screen.findByText("guest")).toBeDefined();
  });
});
