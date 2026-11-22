package gateway

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

func TestRDPSessionLifecycleAndStreamInterception(t *testing.T) {
	now := time.Now().UTC()
	leaseDeadline := now.Add(5 * time.Minute)
	grantExpiry := now.Add(30 * time.Minute)

	var recordedEvent map[string]interface{}
	var mu sync.Mutex

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/internal/v1/sessions/ses_rdp_01/events" {
			var body map[string]interface{}
			_ = json.NewDecoder(r.Body).Decode(&body)
			mu.Lock()
			recordedEvent = body
			mu.Unlock()
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "accepted"})
			return
		}
		http.NotFound(w, r)
	}))
	defer ts.Close()

	cpClient := NewControlPlaneClient(ts.URL, "gw_lab_01", "sec")

	// Create pipe connections simulating client <-> gateway <-> target
	clientConn, clientPeer := net.Pipe()
	targetConn, targetPeer := net.Pipe()

	tunnelParams := &RDPTunnelResponse{
		SessionID:               "ses_rdp_01",
		GrantID:                 "grn_rdp_01",
		TunnelToken:             "hmac_token_123",
		Hostname:                "10.0.2.100",
		Port:                    3389,
		Username:                "Administrator",
		Protocol:                "rdp",
		Security:                "nla",
		DisableClipboard:        true,
		DisableDriveRedirection: true,
		DisableAudio:            true,
		DisablePrinting:         true,
		EnableRecording:         true,
		RecordingName:           "rdp_ses_rdp_01",
		LeaseDeadline:           leaseDeadline.Format(time.RFC3339),
	}

	sess := NewActiveRDPSession(
		context.Background(),
		"ses_rdp_01",
		"grn_rdp_01",
		clientConn,
		targetConn,
		cpClient,
		tunnelParams,
		leaseDeadline,
		grantExpiry,
	)

	// Run session in background
	errCh := make(chan error, 1)
	go func() {
		errCh <- sess.Run()
	}()

	// 1. Client sends user input (e.g. keyboard keystroke) -> Target receives
	clientInput := []byte("type:key,code:65,state:down;")
	go func() {
		_, _ = clientPeer.Write(clientInput)
	}()

	targetBuf := make([]byte, 1024)
	n, err := targetPeer.Read(targetBuf)
	if err != nil {
		t.Fatalf("target failed to read client input: %v", err)
	}
	if string(targetBuf[:n]) != string(clientInput) {
		t.Errorf("expected target to receive %s, got %s", clientInput, targetBuf[:n])
	}

	// 2. Target sends display output -> Client receives
	displayOutput := []byte("4.sync,1.0;4.rect,1.0,1.0,2.10,2.10;")
	go func() {
		_, _ = targetPeer.Write(displayOutput)
	}()

	clientBuf := make([]byte, 1024)
	n, err = clientPeer.Read(clientBuf)
	if err != nil {
		t.Fatalf("client failed to read display output: %v", err)
	}
	if string(clientBuf[:n]) != string(displayOutput) {
		t.Errorf("expected client to receive %s, got %s", displayOutput, clientBuf[:n])
	}

	// 3. Close the peer connection to finish session
	_ = clientPeer.Close()
	_ = targetPeer.Close()

	select {
	case err := <-errCh:
		if err != nil {
			t.Fatalf("Run returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("session did not exit within timeout")
	}

	// 4. Verify recorder summary captured both streams
	summary := sess.Recorder.GetSummary()
	expectedBytes := len(clientInput) + len(displayOutput)
	if summary.SizeBytes != expectedBytes {
		t.Errorf("expected recorder size %d, got %d", expectedBytes, summary.SizeBytes)
	}
	if summary.DigestSHA256 == "" {
		t.Error("expected non-empty SHA256 digest")
	}

	// 5. Verify termination event dispatched to Control Plane
	time.Sleep(50 * time.Millisecond)
	mu.Lock()
	defer mu.Unlock()
	if recordedEvent == nil {
		t.Fatal("expected control plane to receive termination event")
	}
	if recordedEvent["state"] != "ended" {
		t.Errorf("expected state ended, got %v", recordedEvent["state"])
	}
	if recordedEvent["recording"] == nil {
		t.Error("expected recording metadata in termination event payload")
	}
}

func TestRDPSessionLeaseWatcherRevocationTermination(t *testing.T) {
	now := time.Now().UTC()
	// Lease deadline within renewal threshold (< 60s)
	leaseDeadline := now.Add(20 * time.Second)
	grantExpiry := now.Add(10 * time.Minute)

	var terminationReceived bool
	var mu sync.Mutex

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/internal/v1/sessions/ses_rdp_revoked/renew":
			// Simulate rejected lease renewal because grant was revoked
			w.WriteHeader(http.StatusConflict)
			_ = json.NewEncoder(w).Encode(map[string]string{
				"error": "Cannot renew: session is terminating, grant is revoked",
			})
		case "/internal/v1/sessions/ses_rdp_revoked/events":
			mu.Lock()
			terminationReceived = true
			mu.Unlock()
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "accepted"})
		default:
			http.NotFound(w, r)
		}
	}))
	defer ts.Close()

	cpClient := NewControlPlaneClient(ts.URL, "gw_lab_01", "sec")

	clientConn, clientPeer := net.Pipe()
	targetConn, targetPeer := net.Pipe()
	defer clientPeer.Close()
	defer targetPeer.Close()

	sess := NewActiveRDPSession(
		context.Background(),
		"ses_rdp_revoked",
		"grn_rdp_revoked",
		clientConn,
		targetConn,
		cpClient,
		nil,
		leaseDeadline,
		grantExpiry,
	)

	// Run session in background
	errCh := make(chan error, 1)
	go func() {
		errCh <- sess.Run()
	}()

	// leaseWatcher checks every 2s; renewal fails with 409, triggering termination within ~2-3 seconds
	select {
	case <-errCh:
		// Session terminated successfully
	case <-time.After(5 * time.Second):
		t.Fatal("session was not revoked and terminated within 5s")
	}

	mu.Lock()
	defer mu.Unlock()
	if !terminationReceived {
		t.Error("expected control plane to receive confirmed termination event")
	}
}

func TestRDPSessionRecordingFailureTermination(t *testing.T) {
	now := time.Now().UTC()
	leaseDeadline := now.Add(10 * time.Minute)
	grantExpiry := now.Add(30 * time.Minute)

	var reportedGap bool
	var mu sync.Mutex

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/internal/v1/sessions/ses_rdp_rec_fail/events" {
			var body map[string]interface{}
			_ = json.NewDecoder(r.Body).Decode(&body)
			mu.Lock()
			if rec, ok := body["recording"].(map[string]interface{}); ok {
				if rec["coverage_status"] == "gap" {
					reportedGap = true
				}
			}
			mu.Unlock()
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "accepted"})
			return
		}
		http.NotFound(w, r)
	}))
	defer ts.Close()

	cpClient := NewControlPlaneClient(ts.URL, "gw_lab_01", "sec")

	clientConn, clientPeer := net.Pipe()
	targetConn, targetPeer := net.Pipe()
	defer clientPeer.Close()
	defer targetPeer.Close()

	sess := NewActiveRDPSession(
		context.Background(),
		"ses_rdp_rec_fail",
		"grn_rdp_rec_fail",
		clientConn,
		targetConn,
		cpClient,
		nil,
		leaseDeadline,
		grantExpiry,
	)

	// Configure a failing sink with small buffer and short grace period (100ms)
	failingSink := NewMemoryRecordingSink()
	failingSink.SetFailing(true)
	customRecorder := NewSessionRecorder(
		"ses_rdp_rec_fail",
		failingSink,
		64,             // tiny buffer of 64 bytes
		100*time.Millisecond, // 100ms grace period
		func(reason string) {
			sess.Close(reason)
		},
	)
	sess.SetRecorder(customRecorder)

	errCh := make(chan error, 1)
	go func() {
		errCh <- sess.Run()
	}()

	// Write enough bytes from client to exhaust buffer and trigger fail-closed termination
	go func() {
		for i := 0; i < 5; i++ {
			_, _ = clientPeer.Write([]byte("some-bulk-windows-gui-interaction-payload-data-exceeding-buffer-limits;"))
			time.Sleep(50 * time.Millisecond)
		}
	}()

	// Consume security warning on client if any
	go func() {
		buf := make([]byte, 1024)
		for {
			_, err := clientPeer.Read(buf)
			if err != nil {
				return
			}
		}
	}()

	select {
	case <-errCh:
		// Terminated fail-closed due to capture loss timeout
	case <-time.After(3 * time.Second):
		t.Fatal("session did not terminate on recording failure")
	}

	time.Sleep(50 * time.Millisecond)
	mu.Lock()
	defer mu.Unlock()
	if !reportedGap {
		t.Error("expected coverage_status 'gap' to be reported to control plane")
	}
}
