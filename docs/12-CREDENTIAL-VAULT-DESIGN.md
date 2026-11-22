# 12 · Credential Vault Design: Ariba PAM

> Ephemeral SSH CA Signing, Secret Custody & Key Lifecycle · 2026-11-22

Ariba PAM replaces reusable static target credentials with ephemeral cryptographic certificates and scoped just-in-time vault secrets.

---

## 1. Ephemeral SSH Certificate Authority (CA)

The primary credential model for Linux infrastructure access in Ariba PAM is **OpenSSH Certificates**:

```
[ Ariba PAM Gateway ]               [ Isolated User CA Signer ]             [ Target Linux Host ]
         │                                       │                                     │
         │ 1. Request Ephemeral Cert             │                                     │
         │    (Grant ID, Principal, User, Key)   │                                     │
         ├──────────────────────────────────────▶│                                     │
         │                                       │ 2. Sign Certificate                 │
         │                                       │    - Principals: target_username    │
         │                                       │    - Validity: +5 minutes           │
         │ 3. Return Signed Certificate          │    - Serial: unique grant/launch ID │
         │◀──────────────────────────────────────┤                                     │
         │                                                                             │
         │ 4. Dial Target SSH with Certificate                                         │
         ├────────────────────────────────────────────────────────────────────────────▶│
         │                                                                             │ 5. Validate CA Sig
         │                                                                             │    & Check Validity
         │ 6. Establish Interactive SSH Session                                        │
         │◀════════════════════════════════════════════════════════════════════════════┤
```

### Key Security Properties
- **Zero Gateway CA Key Exposure**: The SSH Gateway generates an ephemeral in-memory Ed25519 keypair for each connection, sends the public key to the isolated signer, and receives a signed certificate. The Gateway never has access to the User CA private key.
- **Short Validity Window**: Certificates are valid for at most 5 minutes from issuance (just enough time to complete SSH handshake and establish the connection). Standing validity after session setup is meaningless since target OpenSSH only verifies validity at handshake time.
- **Host Trust Pinned**: Target hosts trust only certificates signed by the Ariba PAM User CA public key configured in `/etc/ssh/sshd_config` (`TrustedUserCAKeys /etc/ssh/ariba_user_ca.pub`).

---

## 2. CA Rollover, Revocation & Recovery (T-06)

1. **CA Key Rollover**:
   - The User CA uses Ed25519 private keys stored within dedicated Hardware Security Modules (HSMs) or isolated signing enclaves.
   - Target hosts support dual CA keys during transition windows (`ariba_user_ca_current.pub` and `ariba_user_ca_next.pub`).
   - Rollover is executed without service downtime or disruption to active sessions.
2. **KRL (Key Revocation List)**:
   - For compromised private keys, OpenSSH Key Revocation Lists (`RevokedKeys`) are distributed to target hosts via automated configuration management (Ansible / Puppet).

---

## 3. Scoped Vault-Backed Target Access

When legacy target infrastructure does not support OpenSSH certificates and requires stored static credentials (e.g. database service passwords, legacy network switch accounts):
1. **HashiCorp Vault / Secret Engine Integration**: Secrets reside in an encrypted vault managed under isolated Vault Custodian custody.
2. **Just-In-Time Secret Retrieval**: The Gateway retrieves the credential at the moment of connection establishment over mutual TLS.
3. **Non-Disclosure**: Stored passwords and private keys are never transmitted to the end-user's browser or SSH client. Credentials are injected directly into the gateway-to-target stream.
4. **Automated Post-Session Rotation**: Target accounts configured for stored credentials trigger immediate, automated password rotation upon session termination, rendering previously exposed credentials invalid.
