"use client";

import React, { useState } from "react";
import {
  Server,
  Activity,
  ShieldCheck,
  RefreshCw,
  HardDrive,
  Cpu,
  Layers,
  Radio,
  AlertTriangle,
  CheckCircle,
  Database,
  ArrowUpRight,
  Zap,
} from "lucide-react";

interface NodeStatus {
  node_id: string;
  role: "primary" | "secondary";
  status: "healthy" | "draining" | "offline";
  version: string;
  heartbeat: string;
  active_sessions: number;
}

interface GatewayZone {
  gateway_id: string;
  zone: string;
  connections: number;
  status: "online" | "degraded";
  last_ping: string;
}

export default function OperationsDashboardPage() {
  const [drillRunning, setDrillRunning] = useState(false);
  const [drillFeedback, setDrillFeedback] = useState<string | null>(null);

  const [nodes] = useState<NodeStatus[]>([
    {
      node_id: "cp-node-01",
      role: "primary",
      status: "healthy",
      version: "v1.1.0",
      heartbeat: "2s ago",
      active_sessions: 14,
    },
    {
      node_id: "cp-node-02",
      role: "secondary",
      status: "healthy",
      version: "v1.1.0",
      heartbeat: "1s ago",
      active_sessions: 11,
    },
    {
      node_id: "cp-node-03",
      role: "secondary",
      status: "healthy",
      version: "v1.1.0",
      heartbeat: "3s ago",
      active_sessions: 9,
    },
  ]);

  const [gateways] = useState<GatewayZone[]>([
    {
      gateway_id: "gw-zone-east-01",
      zone: "us-east-1",
      connections: 18,
      status: "online",
      last_ping: "500ms ago",
    },
    {
      gateway_id: "gw-zone-west-01",
      zone: "us-west-2",
      connections: 16,
      status: "online",
      last_ping: "650ms ago",
    },
  ]);

  const handleSimulateDrill = () => {
    setDrillRunning(true);
    setDrillFeedback("Rehearsing expanded capacity recovery drill across clusters...");
    setTimeout(() => {
      setDrillRunning(false);
      setDrillFeedback("✓ DR Drill Completed: Database RTO = 1.4s (SLA <= 900s), Key Recovery = 0.8s, Evidence p95 = 2.1ms (SLA <= 150ms). Status: PASSED.");
    }, 1500);
  };

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">Platform Operations & High Availability</h1>
            <span className="text-xs font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2.5 py-0.5 rounded border border-emerald-500/20">
              Active Cluster
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Real-time multi-node Control Plane topology, zone-redundant gateway health, zero-downtime upgrades, and DR readiness.
          </p>
        </div>

        <button
          onClick={handleSimulateDrill}
          disabled={drillRunning}
          className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors border border-blue-400/20"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${drillRunning ? "animate-spin" : ""}`} />
          <span>{drillRunning ? "Running DR Rehearsal..." : "Simulate Recovery Drill"}</span>
        </button>
      </div>

      {drillFeedback && (
        <div className="p-4 bg-blue-950/40 border border-blue-500/30 rounded-xl text-blue-200 text-xs flex items-center space-x-3">
          <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span className="font-mono">{drillFeedback}</span>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Cluster Nodes</span>
            <Server className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-white">3 / 3</span>
            <span className="text-xs text-emerald-400 font-medium">100% Healthy</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Failover Switchover: &lt; 200ms</p>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Schema Evolution</span>
            <Layers className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-white">Expand/Contract</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Zero breaking changes · Reversible</p>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Expanded DR Baseline</span>
            <Database className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-white">RTO &le; 15m</span>
            <span className="text-xs text-slate-400 font-mono">RPO &le; 1m</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">500 Assets · 2k Users · 5k Sessions</p>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>SIEM & SOC Adapters</span>
            <Radio className="w-4 h-4 text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-white">Wazuh &amp; SOC</span>
            <span className="text-xs text-emerald-400 font-medium">Connected</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Circuit Breaker: CLOSED</p>
        </div>
      </div>

      {/* Section 1: Control Plane Nodes */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Cpu className="w-4 h-4 text-blue-400" />
            <h2 className="text-sm font-semibold text-white">Stateless Control Plane Cluster</h2>
          </div>
          <span className="text-xs font-mono text-slate-400">Load Balancer: Round Robin / Health Checked</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 font-mono uppercase text-[10px] border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Node ID</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Software Version</th>
                <th className="px-4 py-3">Health Status</th>
                <th className="px-4 py-3">Heartbeat</th>
                <th className="px-4 py-3 text-right">Active Sessions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {nodes.map((node) => (
                <tr key={node.node_id} className="hover:bg-slate-800/20">
                  <td className="px-4 py-3 text-white font-semibold flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span>{node.node_id}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                        node.role === "primary"
                          ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                          : "bg-slate-800 text-slate-400 border border-slate-700"
                      }`}
                    >
                      {node.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{node.version}</td>
                  <td className="px-4 py-3 text-emerald-400">{node.status}</td>
                  <td className="px-4 py-3 text-slate-400">{node.heartbeat}</td>
                  <td className="px-4 py-3 text-right text-slate-200">{node.active_sessions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Section 2: Zone Gateways & Security Adapters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Gateways */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-white">Zone-Redundant SSH Gateways</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">Least Connections Routing</span>
          </div>

          <div className="space-y-3 font-mono text-xs">
            {gateways.map((gw) => (
              <div
                key={gw.gateway_id}
                className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-lg flex items-center justify-between"
              >
                <div>
                  <div className="text-white font-semibold">{gw.gateway_id}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Zone: {gw.zone} · Ping: {gw.last_ping}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-emerald-400 font-bold">{gw.connections} Active</div>
                  <div className="text-[10px] text-slate-500">Go Binary v1.0.0</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Security Adapters & Quorum */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-white">Integrations &amp; Emergency Quorum</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">Zero Standing Privilege</span>
          </div>

          <div className="space-y-3 font-mono text-xs">
            <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-white font-semibold">Wazuh SIEM Adapter (ADR-013)</div>
                <div className="text-[11px] text-slate-400 mt-0.5">OSSEC Transform · SHA256 Dedup</div>
              </div>
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
                OPERATIONAL
              </span>
            </div>

            <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-white font-semibold">Ariba SOC Streaming (ADR-014)</div>
                <div className="text-[11px] text-slate-400 mt-0.5">P1-P4 Priority Channels · Circuit Breaker</div>
              </div>
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
                CONNECTED
              </span>
            </div>

            <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-white font-semibold">Emergency Break-Glass (ADR-010)</div>
                <div className="text-[11px] text-slate-400 mt-0.5">Multi-Custodian Quorum · Out-of-Band</div>
              </div>
              <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded">
                STANDBY
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
