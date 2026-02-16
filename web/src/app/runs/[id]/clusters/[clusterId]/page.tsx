"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchCluster, approveCluster } from "@/lib/api";
import { ClusterDetailSchema } from "@/lib/validators";
import type { ClusterDetail } from "@/lib/validators";
import ConfidencePill from "@/components/ConfidencePill";
import { useToastContext } from "@/context/ToastContext";

function entityDisplay(raw: Record<string, unknown> | null, entityType: string): string {
  if (!raw) return "—";
  if (entityType === "contact") {
    const first = (raw.first_name as string) || "";
    const last = (raw.last_name as string) || "";
    const n = `${first} ${last}`.trim();
    return n || (raw.email as string) || "—";
  }
  return (raw.name as string) || (raw.domain as string) || "—";
}

const CONTACT_FIELDS = ["first_name", "last_name", "email", "company_name", "phone", "job_title"];
const COMPANY_FIELDS = ["name", "domain", "city", "state", "country", "industry"];

export default function ClusterDetailPage() {
  const params = useParams();
  const runId = params.id as string;
  const clusterId = params.clusterId as string;
  const [cluster, setCluster] = useState<ClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const { success, error } = useToastContext();

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchCluster(runId, clusterId);
        setCluster(ClusterDetailSchema.parse(data));
      } catch (e) {
        error(e instanceof Error ? e.message : "Failed to load cluster");
      } finally {
        setLoading(false);
      }
    })();
  }, [runId, clusterId, error]);

  const handleApproveAll = async () => {
    setApproving(true);
    try {
      await approveCluster(runId, clusterId);
      success("Cluster approved");
      const data = await fetchCluster(runId, clusterId);
      setCluster(ClusterDetailSchema.parse(data));
    } catch (e) {
      error(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setApproving(false);
    }
  };

  if (loading) return <div className="p-6">Loading...</div>;
  if (!cluster) return <div className="p-6">Cluster not found.</div>;

  const fields = cluster.entity_type === "contact" ? CONTACT_FIELDS : COMPANY_FIELDS;

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
        <Link href="/runs" className="underline hover:text-slate-900">Runs</Link>
        <span>/</span>
        <Link href={`/runs/${runId}`} className="underline hover:text-slate-900">{runId.slice(0, 8)}</Link>
        <span>/</span>
        <Link href={`/runs/${runId}/clusters`} className="underline hover:text-slate-900">Clusters</Link>
        <span>/</span>
        <span className="font-mono">{clusterId.slice(0, 8)}</span>
      </div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Cluster detail</h1>
        <button
          onClick={handleApproveAll}
          disabled={approving}
          className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {approving ? "Approving..." : "Approve entire cluster"}
        </button>
      </div>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-medium text-slate-800">Members</h2>
        <p className="text-sm text-slate-500">
          Recommended survivor:{" "}
          {cluster.members.find((m) => m.id === cluster.recommended_survivor_entity_id)
            ? entityDisplay(
                cluster.members.find((m) => m.id === cluster.recommended_survivor_entity_id)!.raw_json ?? null,
                cluster.entity_type
              )
            : "—"}
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-600">
                <th className="p-2 font-medium">ID</th>
                {fields.map((f) => (
                  <th key={f} className="p-2 font-medium capitalize">{f.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cluster.members.map((m) => (
                <tr key={m.id} className="border-b border-slate-100">
                  <td className="p-2 font-mono text-xs">{m.id.slice(0, 8)}</td>
                  {fields.map((f) => (
                    <td key={f} className="p-2 text-slate-700">
                      {String((m.raw_json ?? {})[f] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-medium text-slate-800">Pairwise matches</h2>
        <ul className="mt-2 space-y-2">
          {cluster.pairwise_matches.map((m) => (
            <li key={m.id} className="flex items-center gap-4 text-sm">
              <ConfidencePill score={m.score} />
              <span className="text-slate-600">
                {entityDisplay(
                  cluster.members.find((e) => e.id === m.a_entity_id)?.raw_json ?? null,
                  cluster.entity_type
                )}{" "}
                vs{" "}
                {entityDisplay(
                  cluster.members.find((e) => e.id === m.b_entity_id)?.raw_json ?? null,
                  cluster.entity_type
                )}
              </span>
              <span className="text-slate-400">{m.status}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
