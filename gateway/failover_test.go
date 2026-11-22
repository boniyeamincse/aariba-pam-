package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// TestControlPlaneClientMultiEndpointFailover verifies that the gateway client
// automatically detects unavailable or failing control plane nodes and seamlessly
// fails over to surviving cluster nodes.
func TestControlPlaneClientMultiEndpointFailover(t *testing.T) {
	var primaryHits int32
	var secondaryHits int32

	// Primary node: Fails with 503 Service Unavailable
	primaryServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&primaryHits, 1)
		http.Error(w, "Node draining / database partition", http.StatusServiceUnavailable)
	}))
	defer primaryServer.Close()

	// Secondary node: Healthy, returns valid launch response
	secondaryServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&secondaryHits, 1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		now := time.Now().UTC()
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"session_id":        "ses_ha_failover_01",
			"grant_id":          "grn_ha_failover_01",
			"target_account_id": "act_ha_01",
			"credential_type":   "ssh_certificate",
			"target_host":       "10.0.1.50",
			"target_port":       22,
			"target_username":   "root",
			"lease_deadline":    now.Add(30 * time.Second).Format(time.RFC3339),
			"grant_expiry":      now.Add(2 * time.Hour).Format(time.RFC3339),
		})
	}))
	defer secondaryServer.Close()

	// Initialize client with primary and secondary endpoints
	endpoints := []string{primaryServer.URL, secondaryServer.URL}
	client := NewControlPlaneClientWithEndpoints(endpoints, "gw_lab_01", "test-secret")

	// Verify initial endpoint is primary
	if client.GetCurrentEndpoint() != primaryServer.URL {
		t.Fatalf("expected initial endpoint %s, got %s", primaryServer.URL, client.GetCurrentEndpoint())
	}

	// Consume launch should failover from primary to secondary
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	launch, err := client.ConsumeLaunch(ctx, "launch_tok_ha_test")
	if err != nil {
		t.Fatalf("expected ConsumeLaunch to succeed via failover, got error: %v", err)
	}

	if launch.SessionID != "ses_ha_failover_01" {
		t.Errorf("expected session_id 'ses_ha_failover_01', got '%s'", launch.SessionID)
	}

	// Verify hit counts: primary was tried and secondary was hit
	if atomic.LoadInt32(&primaryHits) < 1 {
		t.Errorf("expected primary node to be tried at least once")
	}
	if atomic.LoadInt32(&secondaryHits) < 1 {
		t.Errorf("expected secondary node to be called successfully")
	}

	// Verify active endpoint was updated to secondary
	if client.GetCurrentEndpoint() != secondaryServer.URL {
		t.Errorf("expected active endpoint to update to %s, got %s", secondaryServer.URL, client.GetCurrentEndpoint())
	}
}

// TestControlPlaneClientCompleteOutageHandling verifies that when all control plane nodes
// are unavailable, the client returns an aggregated diagnostic error without panics.
func TestControlPlaneClientCompleteOutageHandling(t *testing.T) {
	// Create two dead mock servers
	server1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "Cluster node 1 down", http.StatusBadGateway)
	}))
	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "Cluster node 2 down", http.StatusServiceUnavailable)
	}))
	server1.Close() // Immediately close to simulate connection refused
	server2.Close()

	client := NewControlPlaneClientWithEndpoints([]string{server1.URL, server2.URL}, "gw_lab_01", "test-secret")

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, err := client.ConsumeLaunch(ctx, "launch_tok_dead_cluster")
	if err == nil {
		t.Fatalf("expected error on complete control plane outage, got nil")
	}
}
