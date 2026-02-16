"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchRun, exportCsv, exportClay, exportN8n } from "@/lib/api";
import { RunDetailSchema } from "@/lib/validators";
import type { RunDetail } from "@/lib/validators";
import { useToastContext } from "@/context/ToastContext";

export default function ActivationPage() {
  const params = useParams();
  const runId = params.id as string;
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const { success, error } = useToastContext();

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchRun(runId);
        setRun(RunDetailSchema.parse(data));
      } catch (e) {
        error(e instanceof Error ? e.message : "Failed to load run");
      } finally {
        setLoading(false);
      }
    })();
  }, [runId, error]);

  const handleExportCsv = async () => {
    setBusy("csv");
    try {
      const blob = await exportCsv(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dedup_export_${run?.entity_type ?? "run"}_${runId.slice(0, 8)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      success("CSV downloaded");
    } catch (e) {
      error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  const handleSendToClay = async () => {
    setBusy("clay");
    try {
      await exportClay(runId);
      success("Sent to Clay");
    } catch (e) {
      error(e instanceof Error ? e.message : "Send to Clay failed");
    } finally {
      setBusy(null);
    }
  };

  const handleTriggerN8n = async () => {
    setBusy("n8n");
    try {
      await exportN8n(runId);
      success("n8n triggered");
    } catch (e) {
      error(e instanceof Error ? e.message : "Trigger n8n failed");
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <div className="p-6">Loading...</div>;
  if (!run) return <div className="p-6">Run not found.</div>;

  return (
    <div className="mx-auto max-w-2xl p-6">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
        <Link href="/runs" className="underline hover:text-slate-900">Runs</Link>
        <span>/</span>
        <Link href={`/runs/${runId}`} className="underline hover:text-slate-900">{runId.slice(0, 8)}</Link>
        <span>/</span>
        <span>Export and webhooks</span>
      </div>
      <h1 className="text-2xl font-semibold text-slate-900">Activation</h1>
      <p className="mt-1 text-sm text-slate-500">
        Export approved survivors or send them to Clay or n8n. Approve matches or clusters first to select survivors.
      </p>

      <div className="mt-6 space-y-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="font-medium text-slate-800">Export CSV</h2>
          <p className="mt-1 text-sm text-slate-500">
            Download a CSV of approved survivor entities.
          </p>
          <button
            onClick={handleExportCsv}
            disabled={busy !== null}
            className="mt-3 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy === "csv" ? "Exporting..." : "Export CSV"}
          </button>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="font-medium text-slate-800">Send to Clay</h2>
          <p className="mt-1 text-sm text-slate-500">
            POST approved survivors to the configured Clay webhook URL.
          </p>
          <button
            onClick={handleSendToClay}
            disabled={busy !== null}
            className="mt-3 rounded border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {busy === "clay" ? "Sending..." : "Send to Clay"}
          </button>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="font-medium text-slate-800">Trigger n8n</h2>
          <p className="mt-1 text-sm text-slate-500">
            POST approved survivors to the configured n8n webhook URL.
          </p>
          <button
            onClick={handleTriggerN8n}
            disabled={busy !== null}
            className="mt-3 rounded border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {busy === "n8n" ? "Triggering..." : "Trigger n8n"}
          </button>
        </div>
      </div>
    </div>
  );
}
