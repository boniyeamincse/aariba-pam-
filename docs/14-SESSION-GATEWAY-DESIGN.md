# 14 · Session Gateway Design: Ariba PAM

> Go SSH Gateway Architecture, Host Pinning & Lease Enforcement · 2026-11-22

The Ariba PAM Session Gateway (`gateway/`) is a high-performance, memory-safe network proxy written in Go (`golang.org/x/crypto/ssh`). It bridges workforce SSH clients to target Linux infrastructure without ever exposing direct network routing.

---

## 1. Gateway Lifecycle & Connection Flow

```
[ User SSH Client ]                [ Go SSH Gateway ]               [ Target Linux Host ]
        │                                  │                                  │
        │ 1. ssh -p 2222 launch_tok@gw     │                                  │
        ├─────────────────────────────────▶│                                  │
        │                                  │ 2. POST /internal/v1/launches/consume
        │                                  │    - Validate token digest       │
        │                                  │    - Get target host & port      │
        │                                  │    - Get lease deadline & cert   │
        │                                  │                                  │
        │                                  │ 3. Strict Host Key Check         │
        │                                  │    - Validate SHA256 fingerprint │
        │                                  ├─────────────────────────────────▶│
        │                                  │ 4. Dial Target with Ephem Cert   │
        │                                  │◀─────────────────────────────────┤
        │ 5. Session Established           │                                  │
        │    & PTY Forwarded               │ 6. Pipe Bi-Directional Traffic   │
        │◀═════════════════════════════════┼═════════════════════════════════▶│
        │                                  │                                  │
        │                                  │ 7. Bounded Lease Watcher Loop    │
        │                                  │    - POST /renew every 30s       │
        │                                  │    - Stream Asciinema Recording  │
        │                                  │                                  │
        │ 8. Grant Expired / Terminated    │                                  │
        │◀─────────────────────────────────┼─────────────────────────────────▶│
        │    Close Sockets & Report Final Event to Control Plane              │
```

---

## 2. Strict Target Host Key Verification (T-03)

To prevent Man-in-the-Middle (MITM) attacks and unauthorized DNS/IP spoofing:
- Every asset onboarded into Ariba PAM must have its public host key fingerprint pinned (`assets.host_trust_ref`, e.g., `SHA256:4Q4r82x9...`).
- When dialing the target, the Gateway executes `hostKeyCallback`:
  ```go
  func (v *PinnedHostKeyVerifier) Verify(hostname string, remote net.Addr, key ssh.PublicKey) error {
      fingerprint := ssh.FingerprintSHA256(key)
      if fingerprint != v.expectedFingerprint {
          return fmt.Errorf("SECURITY ALERT: Host key mismatch! Expected %s, got %s",
              v.expectedFingerprint, fingerprint)
      }
      return nil
  }
  ```
- **Fail-Closed Rule**: If the target's public key does not match or if the asset has unpinned host identity, the gateway aborts the connection immediately before presenting any credentials.

---

## 3. Bounded Leases & Autonomous Local Expiry (T-05, NFR-02)

1. **Lease Calculation**:
   - The lease deadline is strictly calculated as:
     $$\text{LeaseDeadline} = \min(\text{now} + \text{LeaseDurationSeconds}, \text{GrantEffectiveEnd})$$
   - A lease cannot extend past the effective end timestamp of the parent access grant.
2. **Autonomous Enforcement During Partitions**:
   - The Gateway executes an internal timer loop (`session.go`).
   - If a network partition severs communication between the Gateway and the Control Plane, renewal attempts will fail.
   - The Gateway does **not** fail-open; when `time.Now().After(leaseDeadline)`, the Gateway independently closes both client and target connections with zero delay.

---

## 4. Terminal Recording & Fail-Closed Buffering (T-07)

- The Gateway captures all interactive keystrokes, stdout, stderr, and window resize events into asciinema v2 format streams.
- The stream passes through a memory buffer bound for the evidence storage service.
- If storage delivery stalls, the Gateway buffers up to 10 MB. Once the buffer is exhausted, the Gateway pauses interactive input forwarding and displays a warning to the user.
- If storage connectivity is not restored within 30 seconds, the Gateway terminates the session to prevent unrecorded administrative activity.

---

## 5. RDP Gateway Proxy & Windows Infrastructure Support (P6-01, ADR-012)

Ariba PAM extends protocol gateway isolation to Windows infrastructure via the **Guacamole Protocol Daemon (`guacd`) and FreeRDP Engine**:

```
[ Workforce Browser / RDP Client ]        [ Ariba PAM Gateway ]                [ Target Windows Server ]
               │                                   │                                        │
               │ 1. Launch Session (Token)         │                                        │
               ├──────────────────────────────────▶│                                        │
               │                                   │ 2. POST /internal/v1/rdp/tunnel-params │
               │                                   │    - Fetch vault-stored credentials    │
               │                                   │    - Retrieve NLA & policy constraints │
               │                                   │                                        │
               │                                   │ 3. Strict Host Certificate Check       │
               │                                   │    - Validate TLS/NLA thumbprint       │
               │                                   ├───────────────────────────────────────▶│
               │ 4. WebSocket / HTML5 Guac Stream  │ 5. Proxy FreeRDP Protocol Stream       │
               │◀══════════════════════════════════┼═══════════════════════════════════════▶│
               │                                   │                                        │
               │                                   │ 6. Enforce Policy Invariants           │
               │                                   │    - Clipboard: Disabled (Default)     │
               │                                   │    - Drive Redirection: Blocked        │
               │                                   │    - Audio / Printers: Disabled        │
               │                                   │    - Graphic Frame Capture (WORM)      │
               │                                   │                                        │
               │ 7. Lease Expiry / Termination     │ 8. Post-Session Credential Rotation    │
               │◀──────────────────────────────────┼───────────────────────────────────────▶│
```

### Policy Invariants & Security Controls
1. **Clipboard Restriction**: Bi-directional copy/paste between client and target Windows desktop is disabled by default to prevent data exfiltration. Can only be selectively overridden through four-eyes reviewed access policies.
2. **Drive & Storage Redirection Denial**: Client-side drives, folders, and USB devices are strictly prohibited from mounting on the target Windows system.
3. **NLA Authentication & Vault Credentials**: Windows passwords are never disclosed to the operator; credentials are retrieved JIT from the encrypted Vault and injected directly into the FreeRDP handshake.
4. **Post-Session Automated Rotation**: Session closure immediately triggers an automated password change on the target account, preventing credential re-use.
5. **Graphics Session Recording**: The gateway captures visual frame streams with periodic keyframe hashing and SHA-256 integrity digests for WORM evidence preservation.

