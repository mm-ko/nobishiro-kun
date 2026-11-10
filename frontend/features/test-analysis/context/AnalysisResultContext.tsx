"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { StageBResultResponse } from "@/types/api";

type AnalysisResultContextValue = {
  analysisResult: StageBResultResponse | null;
  setAnalysisResult: (result: StageBResultResponse) => void;
  clearAnalysisResult: () => void;
};

const AnalysisResultContext = createContext<AnalysisResultContextValue | null>(
  null,
);

export function AnalysisResultProvider({ children }: { children: ReactNode }) {
  const [analysisResult, setAnalysisResultState] =
    useState<StageBResultResponse | null>(null);

  const setAnalysisResult = useCallback((result: StageBResultResponse) => {
    setAnalysisResultState(result);
  }, []);

  const clearAnalysisResult = useCallback(() => {
    setAnalysisResultState(null);
  }, []);

  const value = useMemo(
    () => ({ analysisResult, setAnalysisResult, clearAnalysisResult }),
    [analysisResult, clearAnalysisResult, setAnalysisResult],
  );

  return (
    <AnalysisResultContext.Provider value={value}>
      {children}
    </AnalysisResultContext.Provider>
  );
}

export function useAnalysisResult() {
  const context = useContext(AnalysisResultContext);

  if (!context) {
    throw new Error(
      "useAnalysisResult は AnalysisResultProvider の内側で使ってください",
    );
  }

  return context;
}
