"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchClusters } from "@/lib/api";
import { z } from "zod";
import { ClusterSummarySchema } from "@/lib/validators";
import { useToastContext } from "@/context/ToastContext";

const ClusterListSchema = z.array(ClusterSummarySchema);

export default function ClustersPage() {
  const params = useParams();
  const runId = params.id as string;
  const [clusters, setClusters] = useState<z.infer<typeof ClusterSummarySchema>[]>([]);
  const [loading, setLoading] = useState(true);
  const { error } = useToastContext();

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchClusters(runId);
        setClusters(ClusterListSchema.parse(data));
      } catch (e) {
        error(e instanceof Error ? e.message : "Failed to load clusters");
      } finally {
        setLoading(false);
      }
    })();
  }, [runId, error]);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
        <Link href="/runs" className="underline hover:text-slate-900">Runs</Link>
        <span>/</span>
        <Link href={`/runs/${runId}`} className="underline hover:text-slate-900">{runId.slice(0, 8)}</Link>
        <span>/</span>
        <span>Clusters</span>
      </div>
      <h1 className="text-2xl font-semibold text-slate-900">Clusters</h1>

      {loading ? (
        <p className="mt-6 text-sm text-slate-500">Loading...</p>
      ) : clusters.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">No clusters.</p>
      ) : (
        <ul className="mt-6 space-y-2">
          {clusters.map((c) => (
            <li key={c.id}>
              <Link
                href={`/runs/${runId}/clusters/${c.id}`}
                className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-500">{c.id.slice(0, 8)}</span>
                  <span className="text-sm text-slate-600">{c.member_count} members</span>
                </div>
                <p className="mt-1 text-sm font-medium text-slate-800">
                  Recommended survivor: {c.recommended_survivor_name ?? "—"}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
