import { getApp, getApps, initializeApp } from "firebase/app";
import {
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

function getFirebaseAuth() {
  const missingConfig = Object.entries(firebaseConfig)
    .filter(([, value]) => !value)
    .map(([key]) => key);

  if (missingConfig.length > 0) {
    throw new Error(
      `Firebaseの設定が不足しています: ${missingConfig.join(", ")}`,
    );
  }

  const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
  return getAuth(app);
}

export function observeFirebaseAuthState(
  onUserChanged: (user: User | null) => void,
  onError: (error: Error) => void,
) {
  try {
    return onAuthStateChanged(getFirebaseAuth(), onUserChanged, onError);
  } catch (error) {
    onError(
      error instanceof Error
        ? error
        : new Error("Firebaseの初期化に失敗しました。"),
    );
    return () => undefined;
  }
}

export async function loginWithFirebase(email: string, password: string) {
  const credential = await signInWithEmailAndPassword(
    getFirebaseAuth(),
    email,
    password,
  );
  return credential.user;
}

export async function registerWithFirebase(email: string, password: string) {
  const credential = await createUserWithEmailAndPassword(
    getFirebaseAuth(),
    email,
    password,
  );
  return credential.user;
}

export function getCurrentFirebaseUser() {
  return getFirebaseAuth().currentUser;
}

export function logoutFromFirebase() {
  return signOut(getFirebaseAuth());
}
