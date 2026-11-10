"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { clearInitializedMyUser, initializeMyUser } from "@/lib/api/auth";
import {
  loginWithFirebase,
  logoutFromFirebase,
  observeFirebaseAuthState,
  registerWithFirebase,
} from "@/lib/firebase/auth";
import type { UserResponse } from "@/types/api";

type AuthContextValue = {
  user: UserResponse | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const authRevision = useRef(0);

  useEffect(() => {
    return observeFirebaseAuthState(
      (firebaseUser) => {
        const revision = ++authRevision.current;

        if (!firebaseUser) {
          clearInitializedMyUser();
          setUser(null);
          setIsLoading(false);
          return;
        }

        setIsLoading(true);
        void initializeMyUser(firebaseUser)
          .then((currentUser) => {
            if (authRevision.current === revision) {
              setUser(currentUser);
            }
          })
          .catch(async () => {
            if (authRevision.current === revision) {
              setUser(null);
              await logoutFromFirebase().catch(() => undefined);
            }
          })
          .finally(() => {
            if (authRevision.current === revision) {
              setIsLoading(false);
            }
          });
      },
      () => {
        clearInitializedMyUser();
        setUser(null);
        setIsLoading(false);
      },
    );
  }, []);

  async function completeAuthentication(
    authenticate: () => ReturnType<typeof loginWithFirebase>,
  ) {
    let firebaseAuthenticationCompleted = false;
    setIsLoading(true);
    try {
      const firebaseUser = await authenticate();
      firebaseAuthenticationCompleted = true;
      const currentUser = await initializeMyUser(firebaseUser);
      setUser(currentUser);
    } catch (error) {
      setUser(null);
      if (firebaseAuthenticationCompleted) {
        await logoutFromFirebase().catch(() => undefined);
      }
      throw error;
    } finally {
      setIsLoading(false);
    }
  }

  async function login(email: string, password: string) {
    await completeAuthentication(() => loginWithFirebase(email, password));
  }

  async function register(email: string, password: string) {
    await completeAuthentication(() => registerWithFirebase(email, password));
  }

  async function logout() {
    setIsLoading(true);
    try {
      await logoutFromFirebase();
      clearInitializedMyUser();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth は AuthProvider の内側で使ってください");
  }
  return context;
}
