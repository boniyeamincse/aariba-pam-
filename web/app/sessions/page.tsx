"use client";

import React, { useState } from "react";
import { Terminal, ShieldAlert, Power, Clock, Check, AlertOctagon } from "lucide-react";
import { ActiveSession } from "@/lib/api-types";

const mockSessions: ActiveSession[] = [
  {
    id: "ses_01j789active01",
    grant_id: "grnt_01j789abc",
    gateway_id: "gw_zone_lab_01",
    asset_name: "payment-db-01.lab.internal",
    target_host: "10.0.1.50",
    target_username: "dbadmin",
    status: "active",
    started_at: "2026-11-22T17:02:00Z",
    lease_deadline: "2026-11-22T17:15:00Z",
    effective_end_at: "2026-11-22T17:45:00Z",
  },
];

export default function ActiveSessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>(mockSessions);
  const [terminatingNotice, setTerminatingNotice] = useState<string | null>(null);

  const handleKillSession = (sessionId: string) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId
          ? { ...s, status: "ended", termination_reason: "Emergency kill switch invoked by admin" }
          : s
      )
    );
    setTerminatingNotice(`Session ${sessionId} was force terminated. Gateway lease dropped.`);
    setTimeout(() => setTerminatingNotice(null), 3500);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Live Interactive Sessions</h1>
          <p className="text-slate-400 text-sm mt-1">
            Real-time SSH proxy gateway sessions. Bounded local lease timers and kill-switch revocation controls.
          </p>
        </div>
      </div>

      {terminatingNotice && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-400 text-xs flex items-center space-x-2">
          <AlertOctagon className="w-4 h-4" />
          <span>{terminatingNotice}</span>
        </div>
      )}

      {sessions.length === 0 ? (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center">
          <Terminal className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-white">No Active Sessions</h3>
          <p className="text-xs text-slate-400 mt-1">
            All gateway tunnels are idle. No open SSH sessions are currently consuming credentials.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sessions.map((ses) => (
            <div
              key={ses.id}
              className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl p-6 transition-all shadow-sm"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center space-x-3">
                    <span className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg border border-emerald-500/20">
                      <Terminal className="w-5 h-5" />
                    </span>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-base text-white">{ses.asset_name}</span>
                        <span className="font-mono text-xs text-slate-400">({ses.target_host})</span>
                        <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase font-mono">
                          {ses.status}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5 flex items-center space-x-2 font-mono">
                        <span>User: <strong className="text-slate-200">{ses.target_username}</strong></span>
                        <span>·</span>
                        <span>Gateway: {ses.gateway_id}</span>
                        <span>·</span>
                        <span>ID: {ses.id}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pt-1">
                    <div className="flex items-center space-x-1">
                      <Clock className="w-3.5 h-3.5 text-blue-400" />
                      <span>Started: {new Date(ses.started_at).toLocaleTimeString()}</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Clock className="w-3.5 h-3.5 text-amber-400" />
                      <span>Lease Deadline: {new Date(ses.lease_deadline).toLocaleTimeString()}</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Clock className="w-3.5 h-3.5 text-purple-400" />
                      <span>Grant Expiry: {new Date(ses.effective_end_at).toLocaleTimeString()}</span>
                    </div>
                  </div>

                  {ses.termination_reason && (
                    <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded p-2 mt-2">
                      Termination Reason: {ses.termination_reason}
                    </div>
                  )}
                </div>

                <div className="flex items-center space-x-3 flex-shrink-0">
                  {ses.status === "active" ? (
                    <button
                      onClick={() => handleKillSession(ses.id)}
                      className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-rose-600/90 hover:bg-rose-600 text-white text-xs font-semibold rounded-lg transition-colors shadow-sm"
                    >
                      <Power className="w-3.5 h-3.5" />
                      <span>Kill Session</span>
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500 font-mono">Session Closed</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
