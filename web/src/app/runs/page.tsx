"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchRuns, createRun } from "@/lib/api";
import { RunSchema } from "@/lib/validators";
import { z } from "zod";
import { useToastContext } from "@/context/ToastContext";

const RunListSchema = z.array(RunSchema);

export default function RunsPage() {
  const [runs, setRuns] = useState<z.infer<typeof RunSchema>[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [entityType, setEntityType] = useState<"contact" | "company">("contact");
  const [file, setFile] = useState<File | null>(null);
  const { success, error } = useToastContext();

  const load = async () => {
    try {
      const data = await fetchRuns();
      setRuns(RunListSchema.parse(data));
    } catch (e) {
      error(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      error("Select a CSV file");
      return;
    }
    setUploading(true);
    try {
      const data = await createRun(entityType, file);
      const run = RunSchema.parse(data);
      success("Run created");
      window.location.href = `/runs/${run.id}`;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Create failed";
      error(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="text-2xl font-semibold text-slate-900">Runs</h1>

      <form onSubmit={handleCreate} className="mt-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-medium text-slate-800">Create a run</h2>
        <div className="mt-3 flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm text-slate-600">Entity type</label>
            <select
              value={entityType}
              onChange={(e) => setEntityType(e.target.value as "contact" | "company")}
              className="mt-1 rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="contact">Contact</option>
              <option value="company">Company</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-600">CSV file</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 text-sm"
            />
            <p className="mt-0.5 text-xs text-slate-500">CSV only (e.g. HubSpot contact or company export)</p>
          </div>
          <button
            type="submit"
            disabled={uploading}
            className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {uploading ? "Running..." : "Run dedup"}
          </button>
        </div>
      </form>

      <div className="mt-8">
        <h2 className="text-lg font-medium text-slate-800">Recent runs</h2>
        {loading ? (
          <p className="mt-2 text-sm text-slate-500">Loading...</p>
        ) : runs.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No runs yet. Upload a CSV to create one.</p>
        ) : (
          <table className="mt-3 w-full border-collapse rounded-lg border border-slate-200 bg-white text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="p-3 font-medium text-slate-700">ID</th>
                <th className="p-3 font-medium text-slate-700">Type</th>
                <th className="p-3 font-medium text-slate-700">Created</th>
                <th className="p-3 font-medium text-slate-700">Status</th>
                <th className="p-3 font-medium text-slate-700"></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-slate-100">
                  <td className="p-3 font-mono text-xs text-slate-600">{r.id.slice(0, 8)}</td>
                  <td className="p-3 capitalize">{r.entity_type}</td>
                  <td className="p-3 text-slate-600">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="p-3">
                    <span
                      className={
                        r.status === "completed"
                          ? "text-emerald-600"
                          : r.status === "failed"
                            ? "text-red-600"
                            : "text-amber-600"
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="p-3">
                    <Link
                      href={`/runs/${r.id}`}
                      className="text-slate-700 underline hover:text-slate-900"
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
