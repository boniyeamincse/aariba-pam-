"use client";

import React, { useState } from "react";
import { Server, Shield, Key, Plus, Check, AlertCircle } from "lucide-react";
import { Asset } from "@/lib/api-types";

// Synthetic initial assets matching lab fixtures
const initialAssets: Asset[] = [
  {
    id: "ast_pay_01",
    name: "payment-db-01.lab.internal",
    environment: "lab",
    team: "payments",
    zone_id: "zone_lab_01",
    host: "10.0.1.50",
    port: 22,
    is_active: true,
    accounts: [
      {
        id: "acc_pay_admin",
        username: "dbadmin",
        is_active: true,
        requires_ticket: true,
        max_duration_seconds: 3600,
      },
      {
        id: "acc_pay_ro",
        username: "readonly",
        is_active: true,
        requires_ticket: false,
        max_duration_seconds: 7200,
      },
    ],
  },
  {
    id: "ast_auth_01",
    name: "auth-api-01.lab.internal",
    environment: "lab",
    team: "security",
    zone_id: "zone_lab_01",
    host: "10.0.1.60",
    port: 22,
    is_active: true,
    accounts: [
      {
        id: "acc_sec_ops",
        username: "secops",
        is_active: true,
        requires_ticket: true,
        max_duration_seconds: 1800,
      },
    ],
  },
];

export default function AssetCatalogPage() {
  const [assets] = useState<Asset[]>(initialAssets);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string>("");
  const [justification, setJustification] = useState("");
  const [ticketRef, setTicketRef] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null);

  const handleOpenRequest = (asset: Asset) => {
    setSelectedAsset(asset);
    setSelectedAccount(asset.accounts[0]?.id || "");
    setJustification("");
    setTicketRef("");
    setSubmittedStatus(null);
  };

  const handleSubmitRequest = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAsset || !selectedAccount || !justification) return;

    // Simulate instant submit
    setSubmittedStatus("Request submitted successfully! Revision created with ID: rev_" + Math.random().toString(36).substring(7));
    setTimeout(() => {
      setSelectedAsset(null);
      setSubmittedStatus(null);
    }, 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Scoped Asset Catalog</h1>
          <p className="text-slate-400 text-sm mt-1">
            Browse servers within your authorized team scope. Select an asset to request time-limited access.
          </p>
        </div>
      </div>

      {/* Asset Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {assets.map((asset) => (
          <div
            key={asset.id}
            className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl p-6 transition-all shadow-sm"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-blue-600/10 text-blue-400 rounded-lg border border-blue-500/20">
                  <Server className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-white text-base">{asset.name}</h3>
                  <div className="flex items-center space-x-2 mt-1">
                    <span className="text-xs font-mono text-slate-400">{asset.host}:{asset.port}</span>
                    <span className="text-slate-600">·</span>
                    <span className="text-xs uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      {asset.environment}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {asset.team}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-5 pt-4 border-t border-slate-800/80">
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
                Available Target Accounts:
              </div>
              <div className="flex flex-wrap gap-2">
                {asset.accounts.map((acc) => (
                  <span
                    key={acc.id}
                    className="inline-flex items-center space-x-1.5 text-xs font-mono bg-slate-800/80 text-slate-200 px-2.5 py-1 rounded-md border border-slate-700"
                  >
                    <Key className="w-3 h-3 text-emerald-400" />
                    <span>{acc.username}</span>
                    {acc.requires_ticket && (
                      <span className="text-[10px] text-amber-400 font-sans ml-1">(Ticket Req)</span>
                    )}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-5">
              <button
                onClick={() => handleOpenRequest(asset)}
                className="w-full inline-flex items-center justify-center space-x-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4" />
                <span>Request JIT Access</span>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Access Request Modal Dialog */}
      {selectedAsset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-white">Request Access to {selectedAsset.name}</h2>
            <p className="text-xs text-slate-400 mt-1">
              Submit an immutable access request revision. An independent scoped approver must review.
            </p>

            {submittedStatus ? (
              <div className="mt-6 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400 text-sm flex items-center space-x-2">
                <Check className="w-5 h-5 flex-shrink-0" />
                <span>{submittedStatus}</span>
              </div>
            ) : (
              <form onSubmit={handleSubmitRequest} className="mt-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Target Linux Account
                  </label>
                  <select
                    value={selectedAccount}
                    onChange={(e) => setSelectedAccount(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  >
                    {selectedAsset.accounts.map((acc) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.username} (Max: {acc.max_duration_seconds / 60}m)
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Requested Duration (Minutes)
                  </label>
                  <input
                    type="number"
                    min={5}
                    max={60}
                    value={durationMinutes}
                    onChange={(e) => setDurationMinutes(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Ticket Reference (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. INC-4021 or JIRA-1092"
                    value={ticketRef}
                    onChange={(e) => setTicketRef(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Business Justification (Required)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Detailed explanation of why elevated access is required..."
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    required
                    minLength={5}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div className="pt-2 flex items-center justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setSelectedAsset(null)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
                  >
                    Submit Request
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
