"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Server,
  Terminal,
  CheckCircle,
  FileText,
  ShieldAlert,
  ArrowRight,
  TrendingUp,
  Clock,
  ExternalLink,
} from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState({
    totalAssets: 4,
    activeSessions: 1,
    pendingApprovals: 2,
    activeGrants: 3,
  });

  return (
    <div className="space-y-8">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-blue-950/60 to-slate-900 border border-blue-900/40 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Privileged Access Overview</h1>
            <p className="text-slate-400 text-sm mt-1">
              Zero Standing Privilege active. All access grants require multi-step approval and generate ephemeral OpenSSH certificates.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <Link
              href="/assets"
              className="inline-flex items-center space-x-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors shadow-sm"
            >
              <Server className="w-4 h-4" />
              <span>Browse Catalog</span>
            </Link>
            <Link
              href="/sessions"
              className="inline-flex items-center space-x-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium px-4 py-2 rounded-lg border border-slate-700 transition-colors"
            >
              <Terminal className="w-4 h-4 text-emerald-400" />
              <span>View Sessions</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider">
            <span>Scoped Assets</span>
            <Server className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-3 text-3xl font-bold text-white">{stats.totalAssets}</div>
          <div className="mt-2 text-xs text-slate-400 flex items-center space-x-1">
            <span className="text-emerald-400">100% scoped</span>
            <span>· All zones protected</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider">
            <span>Pending Approvals</span>
            <CheckCircle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-3 text-3xl font-bold text-amber-400">{stats.pendingApprovals}</div>
          <div className="mt-2 text-xs text-slate-400 flex items-center space-x-1">
            <span>Requires 4-eyes separation</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider">
            <span>Active Live Sessions</span>
            <Terminal className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3 text-3xl font-bold text-emerald-400">{stats.activeSessions}</div>
          <div className="mt-2 text-xs text-slate-400 flex items-center space-x-1">
            <span>Bounded leases active</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider">
            <span>Active Grants</span>
            <Clock className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-3 text-3xl font-bold text-blue-400">{stats.activeGrants}</div>
          <div className="mt-2 text-xs text-slate-400 flex items-center space-x-1">
            <span>Max 60-min window</span>
          </div>
        </div>
      </div>

      {/* Quick Launch & Security Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Fast Action Hub */}
        <div className="lg:col-span-2 bg-slate-900/80 border border-slate-800 rounded-xl p-6">
          <h2 className="text-base font-semibold text-white mb-4">Privileged Workflow Shortcuts</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Link
              href="/assets"
              className="p-4 bg-slate-800/40 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 rounded-lg transition-all group"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="p-2 bg-blue-500/10 text-blue-400 rounded-md">
                  <Server className="w-5 h-5" />
                </span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-colors" />
              </div>
              <h3 className="font-medium text-white text-sm">Request Target Access</h3>
              <p className="text-xs text-slate-400 mt-1">
                Select from authorized production or lab Linux hosts and specify ticket justification.
              </p>
            </Link>

            <Link
              href="/approvals"
              className="p-4 bg-slate-800/40 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 rounded-lg transition-all group"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="p-2 bg-amber-500/10 text-amber-400 rounded-md">
                  <CheckCircle className="w-5 h-5" />
                </span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-colors" />
              </div>
              <h3 className="font-medium text-white text-sm">Approvals Queue</h3>
              <p className="text-xs text-slate-400 mt-1">
                Review pending access requests within your assigned organizational scope.
              </p>
            </Link>

            <Link
              href="/requests"
              className="p-4 bg-slate-800/40 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 rounded-lg transition-all group"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="p-2 bg-purple-500/10 text-purple-400 rounded-md">
                  <FileText className="w-5 h-5" />
                </span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-purple-400 transition-colors" />
              </div>
              <h3 className="font-medium text-white text-sm">My Access History</h3>
              <p className="text-xs text-slate-400 mt-1">
                Inspect your past revisions, approvals, active grants, and one-time launch commands.
              </p>
            </Link>

            <Link
              href="/sessions"
              className="p-4 bg-slate-800/40 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 rounded-lg transition-all group"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="p-2 bg-emerald-500/10 text-emerald-400 rounded-md">
                  <Terminal className="w-5 h-5" />
                </span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
              </div>
              <h3 className="font-medium text-white text-sm">Live Gateway Watcher</h3>
              <p className="text-xs text-slate-400 mt-1">
                Monitor active lease expirations, host key fingerprints, and session termination controls.
              </p>
            </Link>
          </div>
        </div>

        {/* Right Column: Security Controls & Invariant Status */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-base font-semibold text-white mb-4">Security Invariants</h2>
            <div className="space-y-3">
              <div className="flex items-start space-x-3 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1.5 flex-shrink-0"></span>
                <div>
                  <span className="font-medium text-white">Default Deny Enforced:</span>
                  <p className="text-slate-400 mt-0.5">All actions rejected without matching policy and role scope.</p>
                </div>
              </div>

              <div className="flex items-start space-x-3 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1.5 flex-shrink-0"></span>
                <div>
                  <span className="font-medium text-white">Anti-Enumeration 404:</span>
                  <p className="text-slate-400 mt-0.5">Out-of-scope resource probes return 404 Not Found, never 403.</p>
                </div>
              </div>

              <div className="flex items-start space-x-3 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1.5 flex-shrink-0"></span>
                <div>
                  <span className="font-medium text-white">Separation of Duties:</span>
                  <p className="text-slate-400 mt-0.5">Requesters cannot self-approve; approvers cannot self-grant.</p>
                </div>
              </div>

              <div className="flex items-start space-x-3 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1.5 flex-shrink-0"></span>
                <div>
                  <span className="font-medium text-white">Transactional Outbox:</span>
                  <p className="text-slate-400 mt-0.5">100% of state transitions committed atomically with audit logs.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800 text-xs text-slate-400 flex items-center justify-between">
            <span>OpenAPI Spec: v3.1</span>
            <span className="text-emerald-400">SOC 2 / ISO 27001</span>
          </div>
        </div>
      </div>
    </div>
  );
}
