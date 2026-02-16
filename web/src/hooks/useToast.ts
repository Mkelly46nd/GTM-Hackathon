"use client";

import { useCallback, useState } from "react";

export type ToastMessage = { id: number; text: string; kind: "success" | "error" };

let id = 0;

export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const add = useCallback((text: string, kind: "success" | "error" = "success") => {
    const next = id++;
    setToasts((prev) => [...prev, { id: next, text, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== next));
    }, 4000);
  }, []);

  const success = useCallback((text: string) => add(text, "success"), [add]);
  const error = useCallback((text: string) => add(text, "error"), [add]);

  return { toasts, success, error };
}
