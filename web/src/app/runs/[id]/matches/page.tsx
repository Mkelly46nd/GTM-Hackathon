"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchMatches, approveMatch, rejectMatch } from "@/lib/api";
import { MatchesListSchema } from "@/lib/validators";
import type { Match } from "@/lib/validators";
import ConfidencePill from "@/components/ConfidencePill";
import { useToastContext } from "@/context/ToastContext";

function entityDisplayName(raw: Record<string, unknown> | null, entityType: string): string {
  if (!raw) return "—";
  if (entityType === "contact") {
    const first = (raw.first_name as string) || "";
    const last = (raw.last_name as string) || "";
    const n = `${first} ${last}`.trim();
    return n || (raw.email as string) || (raw.external_id as string) || "—";
  }
  return (raw.name as string) || (raw.domain as string) || (raw.external_id as string) || "—";
}

export default function MatchesPage() {
  const params = useParams();
  const runId = params.id as string;
  const [items, setItems] = useState<Match[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [scoreBand, setScoreBand] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { success, error } = useToastContext();

  const load = async () => {
    let min_score: number | undefined;
    let max_score: number | undefined;
    if (scoreBand === "high") {
      min_score = 0.95;
    } else if (scoreBand === "medium") {
      min_score = 0.85;
      max_score = 0.95;
    } else if (scoreBand === "low") {
      max_score = 0.85;
    }
    try {
      const data = await fetchMatches(runId, {
        min_score,
        max_score,
        status: statusFilter || undefined,
        limit: 100,
        offset: 0,
      });
      const parsed = MatchesListSchema.parse(data);
      setItems(parsed.items);
      setTotal(parsed.total);
    } catch (e) {
      error(e instanceof Error ? e.message : "Failed to load matches");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    load();
  }, [runId, scoreBand, statusFilter]);

  const setMatchStatus = (matchId: string, status: "approved" | "rejected") => {
    setItems((prev) => prev.map((m) => (m.id === matchId ? { ...m, status } : m)));
  };

  const handleApprove = async (matchId: string) => {
    setMatchStatus(matchId, "approved");
    try {
      await approveMatch(runId, matchId);
      success("Match approved");
    } catch (e) {
      setMatchStatus(matchId, "unreviewed");
      error(e instanceof Error ? e.message : "Approve failed");
    }
  };

  const handleReject = async (matchId: string) => {
    setMatchStatus(matchId, "rejected");
    try {
      await rejectMatch(runId, matchId);
      success("Match rejected");
    } catch (e) {
      setMatchStatus(matchId, "unreviewed");
      error(e instanceof Error ? e.message : "Reject failed");
    }
  };

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
        <Link href="/runs" className="underline hover:text-slate-900">Runs</Link>
        <span>/</span>
        <Link href={`/runs/${runId}`} className="underline hover:text-slate-900">{runId.slice(0, 8)}</Link>
        <span>/</span>
        <span>Matches</span>
      </div>
      <h1 className="text-2xl font-semibold text-slate-900">Review matches</h1>

      <div className="mt-4 flex flex-wrap gap-4">
        <div>
          <label className="block text-xs text-slate-500">Score band</label>
          <select
            value={scoreBand}
            onChange={(e) => setScoreBand(e.target.value)}
            className="mt-1 rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All</option>
            <option value="high">High (0.95+)</option>
            <option value="medium">Medium (0.85 to 0.95)</option>
            <option value="low">Low (&lt;0.85)</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="mt-1 rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {loading ? (
        <p className="mt-6 text-sm text-slate-500">Loading...</p>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="p-3 font-medium text-slate-700">Entity A</th>
                <th className="p-3 font-medium text-slate-700">Entity B</th>
                <th className="p-3 font-medium text-slate-700">Score</th>
                <th className="p-3 font-medium text-slate-700">Top reasons</th>
                <th className="p-3 font-medium text-slate-700">Survivor</th>
                <th className="p-3 font-medium text-slate-700">Status</th>
                <th className="p-3 font-medium text-slate-700">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} className="border-b border-slate-100">
                  <td className="p-3">{entityDisplayName(m.entity_a?.raw_json ?? null, m.entity_type)}</td>
                  <td className="p-3">{entityDisplayName(m.entity_b?.raw_json ?? null, m.entity_type)}</td>
                  <td className="p-3">
                    <ConfidencePill score={m.score} />
                    <span className="ml-1 text-slate-500">{(m.score * 100).toFixed(0)}%</span>
                  </td>
                  <td className="max-w-xs p-3">
                    {(m.reasons_json || []).slice(0, 3).map((r, i) => (
                      <div key={i} className="text-xs text-slate-600">{r.detail}</div>
                    ))}
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {m.recommended_survivor_entity_id
                      ? entityDisplayName(
                          m.entity_a?.id === m.recommended_survivor_entity_id
                            ? m.entity_a?.raw_json ?? null
                            : m.entity_b?.id === m.recommended_survivor_entity_id
                              ? m.entity_b?.raw_json ?? null
                              : null,
                          m.entity_type
                        )
                      : "—"}
                  </td>
                  <td className="p-3">
                    <span
                      className={
                        m.status === "approved"
                          ? "text-emerald-600"
                          : m.status === "rejected"
                            ? "text-red-600"
                            : "text-slate-500"
                      }
                    >
                      {m.status}
                    </span>
                  </td>
                  <td className="p-3">
                    {m.status === "unreviewed" && (
                      <>
                        <button
                          onClick={() => handleApprove(m.id)}
                          className="mr-2 text-emerald-600 underline hover:text-emerald-700"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleReject(m.id)}
                          className="text-red-600 underline hover:text-red-700"
                        >
                          Reject
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && (
            <p className="p-6 text-center text-slate-500">No matches match the filters.</p>
          )}
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">Total: {total}</p>
    </div>
  );
}
