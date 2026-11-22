"use client";

import React, { useState } from "react";
import { CheckCircle, XCircle, ShieldCheck, User, Clock, AlertCircle } from "lucide-react";
import { ApprovalStepItem } from "@/lib/api-types";

const mockApproverQueue: ApprovalStepItem[] = [
  {
    step_id: "stp_01j789step1",
    request_id: "req_01j789xyz",
    revision_id: "rev_01j789123",
    step_order: 1,
    required_role: "team_approver",
    status: "pending",
    asset_name: "auth-api-01.lab.internal",
    target_account: "secops",
    requester_email: "alice@example.test",
    justification: "Applying emergency kernel patch for CVE-2026-9012",
    requested_start_at: "2026-11-22T18:00:00Z",
    requested_end_at: "2026-11-22T18:30:00Z",
    created_at: "2026-11-22T17:05:00Z",
  },
];

export default function ApproverQueuePage() {
  const [queue, setQueue] = useState<ApprovalStepItem[]>(mockApproverQueue);
  const [notification, setNotification] = useState<string | null>(null);

  const handleDecision = (stepId: string, decision: "approved" | "rejected") => {
    setQueue((prev) => prev.filter((item) => item.step_id !== stepId));
    setNotification(`Step ${stepId} was successfully ${decision}. Grant lifecycle updated.`);
    setTimeout(() => setNotification(null), 3000);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Scoped Approver Queue</h1>
          <p className="text-slate-400 text-sm mt-1">
            Review pending access requests requiring your authorization. Separation of Duties strictly enforced.
          </p>
        </div>
      </div>

      {notification && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400 text-xs">
          {notification}
        </div>
      )}

      {queue.length === 0 ? (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center">
          <ShieldCheck className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-white">Approvals Queue Clean</h3>
          <p className="text-xs text-slate-400 mt-1">
            No pending access requests currently require your review within your scoped domain.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {queue.map((item) => (
            <div
              key={item.step_id}
              className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl p-6 transition-all shadow-sm"
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-base text-white">{item.asset_name}</span>
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      account: {item.target_account}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      Step #{item.step_order} ({item.required_role})
                    </span>
                  </div>

                  <div className="flex items-center space-x-4 text-xs text-slate-400">
                    <div className="flex items-center space-x-1">
                      <User className="w-3.5 h-3.5 text-slate-500" />
                      <span>Requester: <strong className="text-slate-300">{item.requester_email}</strong></span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span>Window: {new Date(item.requested_start_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} – {new Date(item.requested_end_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>

                  <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800 text-xs text-slate-300">
                    <span className="text-slate-500 font-medium">Justification: </span>
                    {item.justification}
                  </div>
                </div>

                <div className="flex items-center space-x-3 flex-shrink-0">
                  <button
                    onClick={() => handleDecision(item.step_id, "rejected")}
                    className="inline-flex items-center space-x-1.5 px-3 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-medium rounded-lg transition-colors"
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Reject</span>
                  </button>
                  <button
                    onClick={() => handleDecision(item.step_id, "approved")}
                    className="inline-flex items-center space-x-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors shadow-sm"
                  >
                    <CheckCircle className="w-4 h-4" />
                    <span>Approve Grant</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
