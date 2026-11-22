"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal as TerminalIcon, ShieldCheck, Clock, Power, Play, RotateCcw } from "lucide-react";

interface TerminalProps {
  assetName?: string;
  targetHost?: string;
  targetUsername?: string;
  initialDurationSeconds?: number;
}

interface HistoryEntry {
  command: string;
  output: string[];
}

export default function WebTerminal({
  assetName = "payment-db-01.lab.internal",
  targetHost = "10.0.1.50",
  targetUsername = "payadmin",
  initialDurationSeconds = 1800,
}: TerminalProps) {
  const [secondsRemaining, setSecondsRemaining] = useState(initialDurationSeconds);
  const [isConnected, setIsConnected] = useState(true);
  const [inputVal, setInputVal] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([
    {
      command: "",
      output: [
        "Connecting to Ariba PAM SSH Gateway (gw_zone_lab_01)...",
        "Validating ephemeral Ed25519 OpenSSH User Certificate...",
        "Certificate verified: [Principal: " + targetUsername + ", CA: ariba-pam-user-ca]",
        "Target SSH host key pinned: SHA256:4f3c1fc88909... (Host verification OK)",
        "Interactive pty allocated. Bounded lease timer activated.",
        "Type 'help' for available diagnostic commands.",
      ],
    },
  ]);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Countdown timer
  useEffect(() => {
    if (!isConnected || secondsRemaining <= 0) return;
    const interval = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          setIsConnected(false);
          setHistory((h) => [
            ...h,
            { command: "", output: ["[GATEWAY NOTICE] Lease expired. SSH connection terminated fail-closed."] },
          ]);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isConnected, secondsRemaining]);

  // Auto scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = inputVal.trim();
    if (!cmd || !isConnected) return;

    let output: string[] = [];
    const lower = cmd.toLowerCase();

    if (lower === "help") {
      output = [
        "Ariba PAM Ephemeral Shell - Diagnostic Commands:",
        "  whoami               Show authenticated target username",
        "  uname -a             Show kernel and architecture info",
        "  systemctl status     Check database service status",
        "  uptime               Show server uptime and load averages",
        "  clear                Clear the terminal screen",
        "  exit                 Terminate SSH session",
      ];
    } else if (lower === "whoami") {
      output = [targetUsername];
    } else if (lower === "uname -a") {
      output = ["Linux payment-db-01 6.8.0-45-generic #45-Ubuntu SMP PREEMPT_DYNAMIC x86_64 GNU/Linux"];
    } else if (lower.startsWith("systemctl status")) {
      output = [
        "● postgresql.service - PostgreSQL RDBMS",
        "     Loaded: loaded (/lib/systemd/system/postgresql.service; enabled)",
        "     Active: active (running) since Sun 2026-11-22 06:15:20 UTC; 10h ago",
        "   Main PID: 1042 (postgres)",
        "      Tasks: 8 (limit: 4915)",
        "     Memory: 84.2M",
      ];
    } else if (lower === "uptime") {
      output = [" 17:15:42 up 10:55,  1 user,  load average: 0.12, 0.08, 0.05"];
    } else if (lower === "clear") {
      setHistory([]);
      setInputVal("");
      return;
    } else if (lower === "exit") {
      setIsConnected(false);
      output = ["[GATEWAY NOTICE] User issued exit. Ephemeral lease released."];
    } else {
      output = [`${cmd}: command not found (synthetic sandbox mode)`];
    }

    setHistory((prev) => [...prev, { command: cmd, output }]);
    setInputVal("");
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl flex flex-col h-[650px]">
      {/* Terminal Titlebar */}
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-3">
          <div className="flex space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block"></span>
            <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block"></span>
            <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block"></span>
          </div>
          <div className="flex items-center space-x-2 font-mono text-slate-300">
            <TerminalIcon className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold text-white">{assetName}</span>
            <span className="text-slate-500">({targetHost})</span>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          {/* Certificate Badge */}
          <div className="hidden sm:flex items-center space-x-1 px-2.5 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>OpenSSH CA User Cert Active</span>
          </div>

          {/* Lease Countdown */}
          <div className={`flex items-center space-x-1.5 px-3 py-1 rounded-md font-mono text-xs font-bold ${
            secondsRemaining < 300
              ? "bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse"
              : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
          }`}>
            <Clock className="w-3.5 h-3.5" />
            <span>Lease: {formatTime(secondsRemaining)}</span>
          </div>

          {/* Disconnect Button */}
          {isConnected && (
            <button
              onClick={() => {
                setIsConnected(false);
                setHistory((h) => [...h, { command: "", output: ["[GATEWAY NOTICE] Disconnected by user."] }]);
              }}
              className="p-1.5 text-slate-400 hover:text-rose-400 bg-slate-800/60 hover:bg-rose-500/10 rounded border border-slate-700 transition-colors"
              title="Terminate Connection"
            >
              <Power className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Terminal Output Area */}
      <div
        onClick={() => inputRef.current?.focus()}
        className="flex-1 bg-black p-4 font-mono text-sm overflow-y-auto text-slate-300 space-y-2 select-text"
      >
        {history.map((entry, idx) => (
          <div key={idx} className="space-y-1">
            {entry.command && (
              <div className="flex items-center space-x-2 text-white">
                <span className="text-emerald-400 font-semibold">{targetUsername}@{assetName.split(".")[0]}:~$</span>
                <span>{entry.command}</span>
              </div>
            )}
            {entry.output.map((line, lIdx) => (
              <div
                key={lIdx}
                className={
                  line.startsWith("[GATEWAY")
                    ? "text-amber-400 font-medium"
                    : line.startsWith("Connecting") || line.startsWith("Validating") || line.startsWith("Certificate") || line.startsWith("Target") || line.startsWith("Interactive")
                    ? "text-blue-400/80 text-xs"
                    : "text-slate-300"
                }
              >
                {line}
              </div>
            ))}
          </div>
        ))}

        {/* Active Command Input Line */}
        {isConnected ? (
          <form onSubmit={handleCommand} className="flex items-center space-x-2 pt-1">
            <span className="text-emerald-400 font-semibold">{targetUsername}@{assetName.split(".")[0]}:~$</span>
            <input
              ref={inputRef}
              type="text"
              autoFocus
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              className="flex-1 bg-transparent border-none outline-none text-white font-mono text-sm caret-emerald-400"
            />
          </form>
        ) : (
          <div className="pt-4 text-xs text-rose-400 flex items-center space-x-2">
            <span>[CONNECTION TERMINATED] Session lease closed by security gateway.</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
