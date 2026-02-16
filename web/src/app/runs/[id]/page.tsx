"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchRun } from "@/lib/api";
import { RunDetailSchema } from "@/lib/validators";
import type { RunDetail } from "@/lib/validators";
import { useToastContext } from "@/context/ToastContext";

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const { error } = useToastContext();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchRun(runId);
        const parsed = RunDetailSchema.parse(data);
        if (!cancelled) setRun(parsed);
      } catch (e) {
        if (!cancelled) error(e instanceof Error ? e.message : "Failed to load run");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, error]);

  if (loading) return <div className="p-6">Loading...</div>;
  if (!run) return <div className="p-6">Run not found.</div>;

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
        <Link href="/runs" className="underline hover:text-slate-900">Runs</Link>
        <span>/</span>
        <Link href={`/runs/${runId}`} className="underline hover:text-slate-900">{runId.slice(0, 8)}</Link>
      </div>
      <h1 className="text-2xl font-semibold text-slate-900 capitalize">{run.entity_type} run</h1>
      <p className="mt-1 text-sm text-slate-500">
        Created {new Date(run.created_at).toLocaleString()} · Status: {run.status}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-2xl font-semibold text-slate-900">{run.total_entities}</p>
          <p className="text-sm text-slate-500">Entities</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-2xl font-semibold text-slate-900">{run.total_matches}</p>
          <p className="text-sm text-slate-500">Matches</p>
          <p className="mt-1 text-xs text-slate-400">
            High: {run.matches_high} · Medium: {run.matches_medium} · Low: {run.matches_low}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-2xl font-semibold text-slate-900">{run.total_clusters}</p>
          <p className="text-sm text-slate-500">Clusters</p>
        </div>
      </div>

      <nav className="mt-8 flex flex-wrap gap-4">
        <Link
          href={`/runs/${runId}/matches`}
          className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Review matches
        </Link>
        <Link
          href={`/runs/${runId}/clusters`}
          className="rounded border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Clusters
        </Link>
        <Link
          href={`/runs/${runId}/activation`}
          className="rounded border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Export and webhooks
        </Link>
      </nav>
    </div>
  );
}
