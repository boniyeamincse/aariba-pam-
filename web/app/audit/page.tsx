"use client";

import React from "react";
import AuditPlayer from "@/components/player";

export default function AuditForensicsPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Audit Forensics & Session Playback</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Immutable WORM recording verification, keystroke search, and synchronized video playback.
          </p>
        </div>
      </div>

      <AuditPlayer
        sessionId="ses_01j789active01"
        requester="alice@example.test"
        targetHost="10.0.1.50"
        targetUsername="dbadmin"
        totalDurationSeconds={35}
      />
    </div>
  );
}
