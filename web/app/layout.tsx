import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import {
  ShieldCheck,
  Server,
  FileText,
  CheckCircle,
  Terminal,
  Activity,
  Lock,
  Video,
  Cpu,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Ariba PAM — Zero Standing Privilege Console",
  description: "Enterprise Privileged Access Management and Just-In-Time Gateway",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col">
        {/* Top Header */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-600/20 text-blue-400 rounded-lg border border-blue-500/30">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <span className="font-bold text-lg tracking-tight text-white">ARIBA PAM</span>
                <span className="ml-2 text-xs font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                  Zero Standing Privilege
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Gateway: CONNECTED</span>
              </div>
              <div className="text-xs bg-slate-800 text-slate-300 px-3 py-1.5 rounded-md border border-slate-700 flex items-center space-x-1.5">
                <Lock className="w-3.5 h-3.5 text-blue-400" />
                <span>Ed25519 CA Active</span>
              </div>
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="border-t border-slate-800/60 bg-slate-900/40 px-4 sm:px-6 lg:px-8">
            <div className="max-w-7xl mx-auto flex space-x-1 text-sm font-medium">
              <Link
                href="/"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Activity className="w-4 h-4 text-slate-400" />
                <span>Dashboard</span>
              </Link>
              <Link
                href="/assets"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Server className="w-4 h-4 text-slate-400" />
                <span>Asset Catalog</span>
              </Link>
              <Link
                href="/requests"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <FileText className="w-4 h-4 text-slate-400" />
                <span>Access Requests</span>
              </Link>
              <Link
                href="/approvals"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <CheckCircle className="w-4 h-4 text-slate-400" />
                <span>Approver Queue</span>
              </Link>
              <Link
                href="/sessions"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Terminal className="w-4 h-4 text-slate-400" />
                <span>Active Sessions</span>
              </Link>
              <Link
                href="/terminal"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Terminal className="w-4 h-4 text-emerald-400" />
                <span>Web Terminal</span>
              </Link>
              <Link
                href="/audit"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Video className="w-4 h-4 text-blue-400" />
                <span>Audit Forensics</span>
              </Link>
              <Link
                href="/operations"
                className="px-4 py-2.5 text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-md transition-colors flex items-center space-x-2"
              >
                <Cpu className="w-4 h-4 text-purple-400" />
                <span>Operations</span>
              </Link>
            </div>
          </nav>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        {/* Footer */}
        <footer className="border-t border-slate-800/80 bg-slate-950 py-4 text-center text-xs text-slate-500">
          Ariba PAM Platform · Zero Standing Privilege (ZSP) Architecture · Compliant with ISO 27001 & SOC 2
        </footer>
      </body>
    </html>
  );
}
