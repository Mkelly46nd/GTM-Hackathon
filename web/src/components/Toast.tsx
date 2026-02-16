"use client";

import type { ToastMessage } from "@/hooks/useToast";

export default function Toast({ toasts }: { toasts: ToastMessage[] }) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded-lg px-4 py-2 shadow-lg ${
            t.kind === "success" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
          }`}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
