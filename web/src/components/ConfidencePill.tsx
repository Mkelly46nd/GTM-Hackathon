"use client";

type Band = "High" | "Medium" | "Low";

function bandForScore(score: number): Band {
  if (score >= 0.95) return "High";
  if (score >= 0.85) return "Medium";
  return "Low";
}

const styles: Record<Band, string> = {
  High: "bg-emerald-100 text-emerald-800",
  Medium: "bg-amber-100 text-amber-800",
  Low: "bg-slate-100 text-slate-700",
};

export default function ConfidencePill({ score }: { score: number }) {
  const band = bandForScore(score);
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[band]}`}>
      {band}
    </span>
  );
}
