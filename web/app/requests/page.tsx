"use client";

import React, { useState } from "react";
import { FileText, Clock, AlertTriangle, XCircle, CheckCircle, RotateCcw } from "lucide-react";
import { AccessRequestSummary } from "@/lib/api-types";

const mockRequests: AccessRequestSummary[] = [
  {
    id: "req_01j789abc",
    requester_id: "usr_alice",
    asset_id: "ast_pay_01",
    asset_name: "payment-db-01.lab.internal",
    target_account_username: "dbadmin",
    status: "approved",
    current_revision_id: "rev_01j789def",
    requested_start_at: "2026-11-22T17:00:00Z",
    requested_end_at: "2026-11-22T17:45:00Z",
    justification: "Investigating replication latency on production shard 01",
    created_at: "2026-11-22T16:58:00Z",
  },
  {
    id: "req_01j789xyz",
    requester_id: "usr_alice",
    asset_id: "ast_auth_01",
    asset_name: "auth-api-01.lab.internal",
    target_account_username: "secops",
    status: "pending",
    current_revision_id: "rev_01j789123",
    requested_start_at: "2026-11-22T18:00:00Z",
    requested_end_at: "2026-11-22T18:30:00Z",
    justification: "Applying emergency kernel patch for CVE-2026-9012",
    created_at: "2026-11-22T17:05:00Z",
  },
];

export default function AccessRequestsPage() {
  const [requests, setRequests] = useState<AccessRequestSummary[]>(mockRequests);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const handleCancel = (reqId: string) => {
    setRequests((prev) =>
      prev.map((r) => (r.id === reqId ? { ...r, status: "cancelled" } : r))
    );
    setActionNotice(`Request ${reqId} has been cancelled.`);
    setTimeout(() => setActionNotice(null), 3000);
  };

  const statusBadge = (status: AccessRequestSummary["status"]) => {
    switch (status) {
      case "approved":
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle className="w-3 h-3" />
            <span className="capitalize">{status}</span>
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3 h-3" />
            <span className="capitalize">{status}</span>
          </span>
        );
      case "cancelled":
      case "rejected":
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3 h-3" />
            <span className="capitalize">{status}</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400">
            <span className="capitalize">{status}</span>
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Access Request History</h1>
          <p className="text-slate-400 text-sm mt-1">
            Review submitted access requests, current revision status, and approval progress.
          </p>
        </div>
      </div>

      {actionNotice && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-blue-400 text-xs">
          {actionNotice}
        </div>
      )}

      {/* Table Container */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/60 border-b border-slate-800 text-slate-400 uppercase text-[11px] font-semibold tracking-wider">
              <tr>
                <th className="py-3.5 px-4">Request / Revision</th>
                <th className="py-3.5 px-4">Target Asset</th>
                <th className="py-3.5 px-4">Account</th>
                <th className="py-3.5 px-4">Window</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4">Justification</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {requests.map((req) => (
                <tr key={req.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-4 px-4">
                    <div className="font-mono text-xs text-white">{req.id}</div>
                    <div className="font-mono text-[11px] text-slate-500">{req.current_revision_id}</div>
                  </td>
                  <td className="py-4 px-4 font-medium text-slate-200">
                    {req.asset_name}
                  </td>
                  <td className="py-4 px-4">
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {req.target_account_username}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-xs text-slate-400">
                    <div>{new Date(req.requested_start_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                    <div className="text-[11px] text-slate-500">to {new Date(req.requested_end_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                  </td>
                  <td className="py-4 px-4">
                    {statusBadge(req.status)}
                  </td>
                  <td className="py-4 px-4 text-xs text-slate-300 max-w-xs truncate" title={req.justification}>
                    {req.justification}
                  </td>
                  <td className="py-4 px-4 text-right">
                    {req.status === "pending" && (
                      <button
                        onClick={() => handleCancel(req.id)}
                        className="text-xs text-rose-400 hover:text-rose-300 font-medium px-2 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 transition-colors"
                      >
                        Cancel
                      </button>
                    )}
                    {req.status === "approved" && (
                      <span className="text-xs text-emerald-400 font-mono">Grant Active</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
