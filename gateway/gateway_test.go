package gateway

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"golang.org/x/crypto/ssh"
)

func TestHostKeyVerification(t *testing.T) {
	// Generate key
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}
	sshPub, err := ssh.NewPublicKey(pub)
	if err != nil {
		t.Fatalf("failed to create ssh public key: %v", err)
	}

	fingerprint := ComputeKeyFingerprint(sshPub)
	if fingerprint == "" {
		t.Fatal("expected non-empty fingerprint")
	}

	dummyAddr, _ := net.ResolveTCPAddr("tcp", "10.0.1.50:22")

	// 1. Matches expected fingerprint
	verifier := TrustedHostKeyVerifier(fingerprint)
	if err := verifier("10.0.1.50:22", dummyAddr, sshPub); err != nil {
		t.Errorf("expected matching fingerprint to pass, got: %v", err)
	}

	// 2. Mismatch fails before credentials presented
	badVerifier := TrustedHostKeyVerifier("SHA256:0000000000000000000000000000000000000000000000000000000000000000")
	if err := badVerifier("10.0.1.50:22", dummyAddr, sshPub); err == nil {
		t.Error("expected mismatch to fail, but it passed")
	}

	// 3. Empty fingerprint fails closed
	emptyVerifier := TrustedHostKeyVerifier("")
	if err := emptyVerifier("10.0.1.50:22", dummyAddr, sshPub); err == nil {
		t.Error("expected empty fingerprint to fail closed, but it passed")
	}
}

func TestControlPlaneClientConsumeAndRenew(t *testing.T) {
	now := time.Now().UTC()
	leaseDeadline := now.Add(5 * time.Minute)
	grantExpiry := now.Add(30 * time.Minute)

	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		secret := r.Header.Get("X-Gateway-Secret")
		if secret != "test-secret" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		switch r.URL.Path {
		case "/internal/v1/launches/consume":
			var req map[string]string
			_ = json.NewDecoder(r.Body).Decode(&req)
			if req["launch_token"] == "valid_token" {
				w.WriteHeader(http.StatusCreated)
				_ = json.NewEncoder(w).Encode(map[string]interface{}{
					"session_id":      "ses_test_01",
					"grant_id":        "grn_test_01",
					"target_host":     "10.0.1.50",
					"target_port":     22,
					"target_username": "dbadmin",
					"lease_deadline":  leaseDeadline.Format(time.RFC3339),
					"grant_expiry":    grantExpiry.Format(time.RFC3339),
				})
			} else {
				w.WriteHeader(http.StatusConflict)
				_ = json.NewEncoder(w).Encode(map[string]string{"code": "LAUNCH_NOT_FOUND"})
			}

		case "/internal/v1/sessions/ses_test_01/renew":
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"session_id":     "ses_test_01",
				"lease_deadline": leaseDeadline.Add(5 * time.Minute).Format(time.RFC3339),
				"grant_expiry":   grantExpiry.Format(time.RFC3339),
			})

		case "/internal/v1/sessions/ses_test_01/events":
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "recorded"})

		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer mockServer.Close()

	client := NewControlPlaneClient(mockServer.URL, "gw_lab_01", "test-secret")

	// 1. Consume valid launch
	resp, err := client.ConsumeLaunch(context.Background(), "valid_token")
	if err != nil {
		t.Fatalf("ConsumeLaunch failed: %v", err)
	}
	if resp.SessionID != "ses_test_01" {
		t.Errorf("expected session_id ses_test_01, got %s", resp.SessionID)
	}
	if resp.TargetHost != "10.0.1.50" {
		t.Errorf("expected target_host 10.0.1.50, got %s", resp.TargetHost)
	}

	// 2. Consume invalid launch fails
	_, err = client.ConsumeLaunch(context.Background(), "invalid_token")
	if err == nil {
		t.Error("expected invalid token to return error")
	}

	// 3. Renew lease succeeds
	renewResp, err := client.RenewLease(context.Background(), "ses_test_01")
	if err != nil {
		t.Fatalf("RenewLease failed: %v", err)
	}
	if renewResp.SessionID != "ses_test_01" {
		t.Errorf("expected session_id ses_test_01, got %s", renewResp.SessionID)
	}

	// 4. Send event succeeds
	err = client.SendEvent(context.Background(), "ses_test_01", "ended", "Normal exit")
	if err != nil {
		t.Fatalf("SendEvent failed: %v", err)
	}
}

func TestActiveSessionLeaseExpiryTermination(t *testing.T) {
	now := time.Now().UTC()
	// Set lease deadline in the past to trigger immediate local termination
	expiredDeadline := now.Add(-1 * time.Second)
	grantExpiry := now.Add(10 * time.Minute)

	clientMock := NewControlPlaneClient("http://mock", "gw_01", "sec")

	sess := NewActiveSession(
		context.Background(),
		"ses_expired_01",
		"grn_01",
		nil,
		nil,
		nil,
		clientMock,
		expiredDeadline,
		grantExpiry,
	)

	// leaseWatcher should detect expiration and cancel context
	go sess.leaseWatcher()

	select {
	case <-sess.cancelCtx.Done():
		// Successfully terminated locally
	case <-time.After(3 * time.Second):
		t.Fatal("session did not terminate locally upon lease expiry")
	}
}
