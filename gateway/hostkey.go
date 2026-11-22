package gateway

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"strings"

	"golang.org/x/crypto/ssh"
)

// ComputeKeyFingerprint returns the SHA256 hex digest of the public key.
func ComputeKeyFingerprint(key ssh.PublicKey) string {
	sum := sha256.Sum256(key.Marshal())
	return "SHA256:" + hex.EncodeToString(sum[:])
}

// TrustedHostKeyVerifier returns an ssh.HostKeyCallback that verifies
// target host keys against an expected fingerprint.
func TrustedHostKeyVerifier(expectedFingerprint string) ssh.HostKeyCallback {
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		if expectedFingerprint == "" {
			// Fail closed: untrusted host without a verified host trust reference
			return fmt.Errorf("host verification failed: no trusted fingerprint configured for target %s", hostname)
		}

		actualFingerprint := ComputeKeyFingerprint(key)
		cleanExpected := strings.TrimSpace(expectedFingerprint)

		if !strings.EqualFold(actualFingerprint, cleanExpected) {
			return fmt.Errorf("host identity mismatch for %s: expected %s, observed %s", hostname, cleanExpected, actualFingerprint)
		}

		return nil
	}
}
