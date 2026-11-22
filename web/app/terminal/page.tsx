"use client";

import React from "react";
import WebTerminal from "@/components/terminal";

export default function TerminalPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">In-Browser Interactive Terminal</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Gateway-mediated SSH shell. Ephemeral OpenSSH Ed25519 Certificate injected automatically.
          </p>
        </div>
      </div>

      <WebTerminal
        assetName="payment-db-01.lab.internal"
        targetHost="10.0.1.50"
        targetUsername="dbadmin"
        initialDurationSeconds={1800}
      />
    </div>
  );
}
