"use client";

import React, { useState, useEffect } from "react";
import { Play, Pause, RotateCcw, FastForward, Search, ShieldCheck, FileCheck, Terminal as TerminalIcon } from "lucide-react";

interface LogFrame {
  timestampSeconds: number;
  text: string;
}

const mockFrames: LogFrame[] = [
  { timestampSeconds: 0, text: "login: payadmin from 10.0.1.200 (gateway-zone-lab-01)" },
  { timestampSeconds: 2, text: "payadmin@payment-db-01:~$ whoami\npayadmin" },
  { timestampSeconds: 6, text: "payadmin@payment-db-01:~$ uname -r\n6.8.0-45-generic" },
  { timestampSeconds: 12, text: "payadmin@payment-db-01:~$ systemctl status postgresql\n● postgresql.service - PostgreSQL RDBMS (active: running)" },
  { timestampSeconds: 20, text: "payadmin@payment-db-01:~$ df -h /var/lib/postgresql\nFilesystem      Size  Used Avail Use% Mounted on\n/dev/nvme0n1p2  200G   45G  145G  24% /var/lib/postgresql" },
  { timestampSeconds: 30, text: "payadmin@payment-db-01:~$ exit\nlogout\nConnection to 10.0.1.50 closed." },
];

export default function AuditPlayer({
  sessionId = "ses_01j789active01",
  requester = "alice@example.test",
  targetHost = "10.0.1.50",
  targetUsername = "payadmin",
  totalDurationSeconds = 35,
  sha256Digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentSecond, setCurrentSecond] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");

  // Playback ticker
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setCurrentSecond((prev) => {
        if (prev >= totalDurationSeconds) {
          setIsPlaying(false);
          return totalDurationSeconds;
        }
        return prev + 1;
      });
    }, 1000 / playbackSpeed);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, totalDurationSeconds]);

  const activeText = mockFrames
    .filter((f) => f.timestampSeconds <= currentSecond)
    .map((f) => f.text)
    .join("\n\n");

  const filteredFrames = mockFrames.filter((f) =>
    f.text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatSeconds = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl flex flex-col">
      {/* Evidence & Integrity Header */}
      <div className="bg-slate-950 px-5 py-4 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-white text-sm">Session Recording: {sessionId}</span>
            <span className="text-emerald-400 font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-[11px]">
              WORM VERIFIED
            </span>
          </div>
          <div className="text-slate-400 mt-1 flex items-center space-x-3 text-[11px] font-mono">
            <span>Requester: {requester}</span>
            <span>·</span>
            <span>Target: {targetUsername}@{targetHost}</span>
          </div>
        </div>

        {/* SHA256 Integrity Chip */}
        <div className="bg-slate-900 border border-slate-800 rounded-md p-2 max-w-sm">
          <div className="text-[10px] uppercase font-semibold text-slate-400 flex items-center space-x-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            <span>SHA-256 Integrity Digest:</span>
          </div>
          <div className="text-[10px] font-mono text-slate-300 truncate" title={sha256Digest}>
            {sha256Digest}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 divide-y lg:divide-y-0 lg:divide-x divide-slate-800 flex-1 min-h-[450px]">
        {/* Terminal Video Player Area */}
        <div className="lg:col-span-2 bg-black p-5 font-mono text-sm text-slate-200 overflow-y-auto flex flex-col justify-between">
          <div className="space-y-3 whitespace-pre-wrap">
            {activeText || (
              <span className="text-slate-600 italic">Press Play to begin session audit replay...</span>
            )}
          </div>
        </div>

        {/* Searchable Keystrokes Sidebar */}
        <div className="p-4 bg-slate-900/60 flex flex-col">
          <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center space-x-1.5">
            <Search className="w-3.5 h-3.5 text-blue-400" />
            <span>Search Transcript</span>
          </div>

          <div className="relative mb-3">
            <input
              type="text"
              placeholder="Filter commands (e.g. whoami, systemctl)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 text-xs">
            {filteredFrames.map((frame, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setCurrentSecond(frame.timestampSeconds);
                  setIsPlaying(false);
                }}
                className={`w-full text-left p-2.5 rounded-lg border transition-all ${
                  currentSecond >= frame.timestampSeconds && (idx === filteredFrames.length - 1 || currentSecond < (filteredFrames[idx + 1]?.timestampSeconds ?? 999))
                    ? "bg-blue-600/20 border-blue-500/40 text-blue-300"
                    : "bg-slate-800/40 hover:bg-slate-800 border-slate-800 text-slate-400"
                }`}
              >
                <div className="flex items-center justify-between font-mono text-[11px] text-slate-500 mb-1">
                  <span>Timestamp: {formatSeconds(frame.timestampSeconds)}</span>
                  <span className="text-blue-400 text-[10px]">Jump ➔</span>
                </div>
                <div className="font-mono text-xs text-slate-200 truncate">{frame.text.split("\n")[0]}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Playback Controls Footer */}
      <div className="bg-slate-950 px-5 py-3 border-t border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors shadow-sm"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </button>

          <button
            onClick={() => {
              setCurrentSecond(0);
              setIsPlaying(false);
            }}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition-colors"
            title="Reset"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          <span className="font-mono text-slate-300">
            {formatSeconds(currentSecond)} / {formatSeconds(totalDurationSeconds)}
          </span>
        </div>

        {/* Timeline Scrubber Slider */}
        <div className="flex-1 mx-6 hidden sm:block">
          <input
            type="range"
            min={0}
            max={totalDurationSeconds}
            value={currentSecond}
            onChange={(e) => {
              setCurrentSecond(Number(e.target.value));
              setIsPlaying(false);
            }}
            className="w-full accent-blue-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg appearance-none"
          />
        </div>

        {/* Speed Toggles */}
        <div className="flex items-center space-x-1.5 bg-slate-900 border border-slate-800 p-1 rounded-lg">
          {[0.5, 1, 2, 4].map((spd) => (
            <button
              key={spd}
              onClick={() => setPlaybackSpeed(spd)}
              className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                playbackSpeed === spd
                  ? "bg-blue-600 text-white font-bold"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {spd}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
