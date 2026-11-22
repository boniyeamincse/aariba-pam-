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
