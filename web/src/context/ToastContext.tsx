"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import Toast from "@/components/Toast";
import type { ToastMessage } from "@/hooks/useToast";

type ToastContextValue = {
  success: (text: string) => void;
  error: (text: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const add = useCallback((text: string, kind: "success" | "error") => {
    const id = toastId++;
    setToasts((prev) => [...prev, { id, text, kind }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const success = useCallback((text: string) => add(text, "success"), [add]);
  const error = useCallback((text: string) => add(text, "error"), [add]);

  return (
    <ToastContext.Provider value={{ success, error }}>
      {children}
      <Toast toasts={toasts} />
    </ToastContext.Provider>
  );
}

export function useToastContext(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToastContext must be used within ToastProvider");
  return ctx;
}
