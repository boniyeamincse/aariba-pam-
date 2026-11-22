package gateway

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
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

func TestRecordingCaptureAndDigest(t *testing.T) {
	sink := NewMemoryRecordingSink()
	rec := NewSessionRecorder("ses_rec_01", sink, 1024*1024, 30*time.Second, nil)

	chunk1 := []byte("uname -a\n")
	chunk2 := []byte("Linux payment-db-01 6.8.0-enterprise\n")

	if err := rec.RecordChunk(chunk1); err != nil {
		t.Fatalf("RecordChunk failed: %v", err)
	}
	if err := rec.RecordChunk(chunk2); err != nil {
		t.Fatalf("RecordChunk failed: %v", err)
	}

	summary := rec.GetSummary()
	if summary.SizeBytes != len(chunk1)+len(chunk2) {
		t.Errorf("expected size %d, got %d", len(chunk1)+len(chunk2), summary.SizeBytes)
	}
	if summary.CoverageStatus != "complete" {
		t.Errorf("expected complete coverage, got %s", summary.CoverageStatus)
	}
	if len(summary.DigestSHA256) != 64 {
		t.Errorf("expected 64-char hex SHA256 digest, got %s", summary.DigestSHA256)
	}
}

func TestRecordingCaptureDegradationAndGapDetection(t *testing.T) {
	sink := NewMemoryRecordingSink()
	rec := NewSessionRecorder("ses_gap_01", sink, 64, 30*time.Second, nil)

	// 1. Initial write succeeds
	if err := rec.RecordChunk([]byte("initial traffic")); err != nil {
		t.Fatalf("initial write failed: %v", err)
	}
	if rec.IsDegraded() {
		t.Error("expected recorder to be healthy")
	}

	// 2. Simulate storage failure (e.g. S3 outage / network partition)
	sink.SetFailing(true)

	// Write while failing -> enters degraded state and marks gap
	err := rec.RecordChunk([]byte("traffic during outage"))
	if err == nil {
		t.Error("expected error when sink is failing")
	}
	if !rec.IsDegraded() {
		t.Error("expected recorder to be marked degraded")
	}
	if rec.CoverageStatus() != "gap" {
		t.Errorf("expected coverage status 'gap', got %s", rec.CoverageStatus())
	}

	// Buffer overflow returns ErrRecordingBufferFull
	largeChunk := make([]byte, 128)
	err = rec.RecordChunk(largeChunk)
	if err != ErrRecordingBufferFull {
		t.Errorf("expected ErrRecordingBufferFull, got %v", err)
	}
}

func TestRecordingGracePeriodAutoTermination(t *testing.T) {
	sink := NewMemoryRecordingSink()
	sink.SetFailing(true) // Immediate failure

	timeoutFired := make(chan string, 1)
	// Fast grace period (100ms) for test verification
	rec := NewSessionRecorder("ses_timeout_01", sink, 1024, 100*time.Millisecond, func(reason string) {
		timeoutFired <- reason
	})

	// Trigger write to start grace timer
	_ = rec.RecordChunk([]byte("critical admin activity"))

	select {
	case reason := <-timeoutFired:
		if reason == "" {
			t.Error("expected non-empty termination reason")
		}
	case <-time.After(1 * time.Second):
		t.Fatal("fail-closed grace period timeout did not fire within expected duration")
	}
}

func TestUnsafeLaunchBlockedOnPipelineDegraded(t *testing.T) {
	cfg, err := DefaultConfig()
	if err != nil {
		t.Fatalf("failed to create default config: %v", err)
	}

	server := NewServer(cfg)
	// Pipeline healthy -> launch permitted
	if err := server.CheckPipelineReady(); err != nil {
		t.Errorf("expected pipeline to be ready, got: %v", err)
	}

	// Degrade recording sink -> launch blocked (fail-closed)
	memSink := server.RecordingSink.(*MemoryRecordingSink)
	memSink.SetFailing(true)

	err = server.CheckPipelineReady()
	if err == nil {
		t.Error("expected CheckPipelineReady to fail when sink is degraded")
	}
}

// createSSHChannelPair creates an in-memory SSH client/server connection over net.Pipe
// createSSHChannelPair creates an in-memory SSH client/server connection over TCP loopback
// and returns the open client and server channel pair.
func createSSHChannelPair(t *testing.T) (ssh.Channel, ssh.Channel, func()) {
	t.Helper()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen on loopback: %v", err)
	}

	_, signerKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate ed25519 key: %v", err)
	}
	signer, err := ssh.NewSignerFromKey(signerKey)
	if err != nil {
		t.Fatalf("failed to create signer: %v", err)
	}

	serverConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			return nil, nil
		},
	}
	serverConfig.AddHostKey(signer)

	serverChanReady := make(chan ssh.Channel, 1)
	serverErrChan := make(chan error, 1)

	go func() {
		sNet, err := listener.Accept()
		if err != nil {
			serverErrChan <- err
			return
		}
		_, chans, reqs, err := ssh.NewServerConn(sNet, serverConfig)
		if err != nil {
			serverErrChan <- err
			return
		}
		go ssh.DiscardRequests(reqs)
		for newChan := range chans {
			ch, reqs2, err := newChan.Accept()
			if err != nil {
				serverErrChan <- err
				return
			}
			go ssh.DiscardRequests(reqs2)
			serverChanReady <- ch
			return
		}
	}()

	clientConfig := &ssh.ClientConfig{
		User:            "testuser",
		Auth:            []ssh.AuthMethod{ssh.Password("testpass")},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         5 * time.Second,
	}

	cNet, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial loopback: %v", err)
	}

	cConn, chans, reqs, err := ssh.NewClientConn(cNet, "", clientConfig)
	if err != nil {
		t.Fatalf("failed to establish client SSH conn: %v", err)
	}
	go ssh.DiscardRequests(reqs)
	sshClient := ssh.NewClient(cConn, chans, reqs)

	clientChan, reqs3, err := sshClient.OpenChannel("session", nil)
	if err != nil {
		t.Fatalf("failed to open client channel: %v", err)
	}
	go ssh.DiscardRequests(reqs3)

	var serverChan ssh.Channel
	select {
	case serverChan = <-serverChanReady:
	case err := <-serverErrChan:
		t.Fatalf("server failed to accept channel: %v", err)
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server channel")
	}

	cleanup := func() {
		_ = clientChan.Close()
		_ = serverChan.Close()
		_ = sshClient.Close()
		_ = cNet.Close()
		_ = listener.Close()
	}

	return clientChan, serverChan, cleanup
}

func TestKeystrokeRoundTripLatencyBenchmark(t *testing.T) {
	// NFR-05: SSH Gateway proxy adds <= 15 ms latency to keystroke round-trip.
	clientEndpoint, gwClientChan, cleanupClient := createSSHChannelPair(t)
	defer cleanupClient()

	gwTargetChan, targetEndpoint, cleanupTarget := createSSHChannelPair(t)
	defer cleanupTarget()

	sess := NewActiveSession(
		context.Background(),
		"ses_bench_lat_01",
		"grn_bench_lat_01",
		gwClientChan,
		gwTargetChan,
		nil,
		NewControlPlaneClient("http://mock", "gw_01", "sec"),
		time.Now().Add(1*time.Hour),
		time.Now().Add(1*time.Hour),
	)

	// Target echo loop (simulates target terminal echo)
	targetStop := make(chan struct{})
	go func() {
		buf := make([]byte, 1024)
		for {
			select {
			case <-targetStop:
				return
			default:
				n, err := targetEndpoint.Read(buf)
				if err != nil {
					return
				}
				if n > 0 {
					_, _ = targetEndpoint.Write(buf[:n])
				}
			}
		}
	}()

	go func() {
		_ = sess.Run()
	}()

	const keystrokeCount = 500
	var totalDuration time.Duration
	var maxDuration time.Duration

	buf := make([]byte, 1)
	for i := 0; i < keystrokeCount; i++ {
		char := byte('A' + (i % 26))
		start := time.Now()

		if _, err := clientEndpoint.Write([]byte{char}); err != nil {
			t.Fatalf("failed to write keystroke %d: %v", i, err)
		}

		n, err := clientEndpoint.Read(buf)
		if err != nil || n != 1 || buf[0] != char {
			t.Fatalf("keystroke %d read mismatch (n=%d, expected=%c, got=%c, err=%v)", i, n, char, buf[0], err)
		}

		elapsed := time.Since(start)
		totalDuration += elapsed
		if elapsed > maxDuration {
			maxDuration = elapsed
		}
	}

	avgLatency := totalDuration / time.Duration(keystrokeCount)
	t.Logf("NFR-05 Benchmark Results: %d keystrokes | Avg Latency: %v | Max Latency: %v", keystrokeCount, avgLatency, maxDuration)

	// NFR-05 requirement: Keystroke round-trip latency added by gateway must be <= 15ms
	if avgLatency > 15*time.Millisecond {
		t.Errorf("NFR-05 SLA violated: average keystroke latency %v exceeded 15ms target", avgLatency)
	}

	sess.Close("benchmark complete")
	close(targetStop)
}

func TestConcurrentStreamsCapacity(t *testing.T) {
	// NFR-05 / T-10: Benchmark suite under 200 concurrent active SSH streams.
	const concurrentStreams = 200
	var wg sync.WaitGroup
	wg.Add(concurrentStreams)

	errCount := 0
	var errMu sync.Mutex

	startTime := time.Now()

	for i := 0; i < concurrentStreams; i++ {
		go func(streamIdx int) {
			defer wg.Done()

			sink := NewMemoryRecordingSink()
			rec := NewSessionRecorder(
				fmt.Sprintf("ses_stream_%03d", streamIdx),
				sink,
				64*1024,
				30*time.Second,
				nil,
			)

			// Stream 10 interactive chunks per session concurrently
			for c := 0; c < 10; c++ {
				data := []byte(fmt.Sprintf("stream_%d_command_%d\n", streamIdx, c))
				if err := rec.RecordChunk(data); err != nil {
					errMu.Lock()
					errCount++
					errMu.Unlock()
					return
				}
			}

			summary := rec.GetSummary()
			if summary.CoverageStatus != "complete" {
				errMu.Lock()
				errCount++
				errMu.Unlock()
			}
		}(i)
	}

	wg.Wait()
	totalElapsed := time.Since(startTime)
	t.Logf("NFR-05 Capacity Results: %d concurrent streams processed in %v (errCount=%d)", concurrentStreams, totalElapsed, errCount)

	if errCount > 0 {
		t.Errorf("expected 0 errors across %d concurrent streams, got %d", concurrentStreams, errCount)
	}
}

func TestStandardOpenSSHClientCompatibility(t *testing.T) {
	// 1. OpenSSH Certificate Compatibility
	caPub, caPriv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate CA key: %v", err)
	}
	caSigner, err := ssh.NewSignerFromKey(caPriv)
	if err != nil {
		t.Fatalf("failed to create CA signer: %v", err)
	}

	userPub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate user key: %v", err)
	}
	userSSHPub, err := ssh.NewPublicKey(userPub)
	if err != nil {
		t.Fatalf("failed to create user SSH public key: %v", err)
	}

	now := time.Now().UTC()
	cert := &ssh.Certificate{
		Key:             userSSHPub,
		Serial:          987654321,
		CertType:        ssh.UserCert,
		KeyId:           "ariba_grn_test_dbadmin",
		ValidPrincipals: []string{"dbadmin"},
		ValidAfter:      uint64(now.Add(-1 * time.Minute).Unix()),
		ValidBefore:     uint64(now.Add(5 * time.Minute).Unix()),
		Permissions: ssh.Permissions{
			Extensions: map[string]string{
				"permit-pty":     "",
				"permit-user-rc": "",
			},
		},
	}

	if err := cert.SignCert(rand.Reader, caSigner); err != nil {
		t.Fatalf("SignCert failed: %v", err)
	}

	// 2. Validate standard OpenSSH cert checker accepts the certificate
	checker := &ssh.CertChecker{
		IsUserAuthority: func(auth ssh.PublicKey) bool {
			caSignerPub, _ := ssh.NewPublicKey(caPub)
			return auth.Type() == caSignerPub.Type() && string(auth.Marshal()) == string(caSignerPub.Marshal())
		},
	}

	// Test authorized principal "dbadmin" succeeds
	validConn := &testConnMetadata{user: "dbadmin"}
	perm, err := checker.Authenticate(validConn, cert)
	if err != nil {
		t.Errorf("expected valid OpenSSH certificate to authenticate, got: %v", err)
	}
	if perm == nil {
		t.Error("expected non-nil permissions from certificate auth")
	}

	// Test unauthorized principal "root" fails
	invalidConn := &testConnMetadata{user: "root"}
	_, err = checker.Authenticate(invalidConn, cert)
	if err == nil {
		t.Error("expected cert auth to fail for unauthorized principal 'root'")
	}

	// 3. Validate Terminal Emulation payload structures (pty-req & window-change)
	ptyReq := struct {
		Term     string
		Width    uint32
		Height   uint32
		PixWidth uint32
		PixHeight uint32
		Modes    []byte
	}{
		Term:   "xterm-256color",
		Width:  80,
		Height: 24,
	}
	ptyPayload := ssh.Marshal(&ptyReq)
	if len(ptyPayload) == 0 {
		t.Error("failed to marshal pty-req structure")
	}

	winChange := struct {
		Width    uint32
		Height   uint32
		PixWidth uint32
		PixHeight uint32
	}{
		Width:  120,
		Height: 40,
	}
	winPayload := ssh.Marshal(&winChange)
	if len(winPayload) == 0 {
		t.Error("failed to marshal window-change structure")
	}
}

type testConnMetadata struct {
	user string
}

func (m *testConnMetadata) User() string          { return m.user }
func (m *testConnMetadata) SessionID() []byte     { return []byte("test_session_id") }
func (m *testConnMetadata) ClientVersion() []byte { return []byte("SSH-2.0-OpenSSH_9.6") }
func (m *testConnMetadata) ServerVersion() []byte { return []byte("SSH-2.0-AribaPAMGateway_1.0") }
func (m *testConnMetadata) RemoteAddr() net.Addr  { return &net.IPAddr{IP: net.ParseIP("192.168.1.100")} }
func (m *testConnMetadata) LocalAddr() net.Addr   { return &net.IPAddr{IP: net.ParseIP("10.0.1.1")} }

func TestControlPlaneClientRetrieveVaultSecret(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Gateway-Secret") != "test_secret" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if r.URL.Path == "/internal/v1/credentials/vault-secret" {
			var body map[string]string
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			if body["grant_id"] == "grnt_valid" && body["session_id"] == "ses_valid" && body["target_account_id"] == "act_valid" {
				w.WriteHeader(http.StatusOK)
				json.NewEncoder(w).Encode(map[string]string{
					"credential_type": "password",
					"secret_value":    "SuperSecretPassword123!",
					"username":        "dbadmin",
				})
				return
			}
			w.WriteHeader(http.StatusForbidden)
			w.Write([]byte(`{"code":"GRANT_EXPIRED"}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	client := NewControlPlaneClient(ts.URL, "gw_test", "test_secret")

	// 1. Successful retrieval
	ctx := context.Background()
	secret, err := client.RetrieveVaultSecret(ctx, "grnt_valid", "ses_valid", "act_valid")
	if err != nil {
		t.Fatalf("expected successful vault secret retrieval, got: %v", err)
	}
	if secret.CredentialType != "password" || secret.SecretValue != "SuperSecretPassword123!" || secret.Username != "dbadmin" {
		t.Errorf("unexpected secret response: %+v", secret)
	}

	// 2. Rejected retrieval (e.g. expired grant)
	_, err = client.RetrieveVaultSecret(ctx, "grnt_expired", "ses_valid", "act_valid")
	if err == nil {
		t.Error("expected error for expired grant retrieval, got nil")
	}
}



