package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// LaunchResponse contains the authorization details returned by the control plane.
type LaunchResponse struct {
	SessionID       string    `json:"session_id"`
	GrantID         string    `json:"grant_id"`
	TargetAccountID string    `json:"target_account_id"`
	CredentialType  string    `json:"credential_type"`
	TargetHost      string    `json:"target_host"`
	TargetPort      int       `json:"target_port"`
	TargetUsername  string    `json:"target_username"`
	LeaseDeadline   time.Time `json:"lease_deadline"`
	GrantExpiry     time.Time `json:"grant_expiry"`
}

// RenewResponse contains the updated lease deadline from renewal.
type RenewResponse struct {
	SessionID     string    `json:"session_id"`
	LeaseDeadline time.Time `json:"lease_deadline"`
	GrantExpiry   time.Time `json:"grant_expiry"`
}

// ControlPlaneClient communicates with the Ariba PAM control plane.
// Supports multi-endpoint failover across redundant control plane instances.
type ControlPlaneClient struct {
	BaseURL    string
	BaseURLs   []string
	activeIdx  int
	mu         sync.RWMutex
	GatewayID  string
	Secret     string
	HTTPClient *http.Client
}

// NewControlPlaneClient initializes a client for internal control plane routes.
// Accepts single URL or comma-separated URLs for multi-node clusters.
func NewControlPlaneClient(baseURL, gatewayID, secret string) *ControlPlaneClient {
	var urls []string
	for _, u := range strings.Split(baseURL, ",") {
		u = strings.TrimSpace(u)
		if u != "" {
			urls = append(urls, strings.TrimRight(u, "/"))
		}
	}
	if len(urls) == 0 {
		urls = []string{"http://localhost:8000"}
	}
	return &ControlPlaneClient{
		BaseURL:    urls[0],
		BaseURLs:   urls,
		GatewayID:  gatewayID,
		Secret:     secret,
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// NewControlPlaneClientWithEndpoints initializes a client with explicit multiple endpoints.
func NewControlPlaneClientWithEndpoints(endpoints []string, gatewayID, secret string) *ControlPlaneClient {
	var urls []string
	for _, u := range endpoints {
		u = strings.TrimSpace(u)
		if u != "" {
			urls = append(urls, strings.TrimRight(u, "/"))
		}
	}
	if len(urls) == 0 {
		urls = []string{"http://localhost:8000"}
	}
	return &ControlPlaneClient{
		BaseURL:    urls[0],
		BaseURLs:   urls,
		GatewayID:  gatewayID,
		Secret:     secret,
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// GetCurrentEndpoint returns the currently active control plane base URL.
func (c *ControlPlaneClient) GetCurrentEndpoint() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.BaseURL
}

// doRequest performs an HTTP request against the active control plane node with automatic failover.
func (c *ControlPlaneClient) doRequest(ctx context.Context, method, path string, bodyBytes []byte) (*http.Response, []byte, error) {
	c.mu.RLock()
	endpoints := make([]string, len(c.BaseURLs))
	copy(endpoints, c.BaseURLs)
	startIdx := c.activeIdx
	c.mu.RUnlock()

	var lastErr error
	n := len(endpoints)
	for i := 0; i < n; i++ {
		idx := (startIdx + i) % n
		endpoint := endpoints[idx]
		url := endpoint + path

		var bodyReader io.Reader
		if bodyBytes != nil {
			bodyReader = bytes.NewReader(bodyBytes)
		}

		req, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
		if err != nil {
			return nil, nil, err
		}
		if bodyBytes != nil {
			req.Header.Set("Content-Type", "application/json")
		}
		req.Header.Set("X-Gateway-Secret", c.Secret)

		resp, err := c.HTTPClient.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("node %s connection error: %w", endpoint, err)
			continue
		}

		// Failover on server unavailability (502, 503, 504) if additional endpoints exist
		if (resp.StatusCode == http.StatusBadGateway || resp.StatusCode == http.StatusServiceUnavailable || resp.StatusCode == http.StatusGatewayTimeout) && i < n-1 {
			resp.Body.Close()
			lastErr = fmt.Errorf("node %s returned status %d", endpoint, resp.StatusCode)
			continue
		}

		respBody, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			lastErr = fmt.Errorf("node %s body read error: %w", endpoint, readErr)
			continue
		}

		// Update active endpoint if failover succeeded
		if idx != startIdx {
			c.mu.Lock()
			c.activeIdx = idx
			c.BaseURL = endpoint
			c.mu.Unlock()
		}

		return resp, respBody, nil
	}

	return nil, nil, fmt.Errorf("all %d control plane endpoints failed, last error: %w", n, lastErr)
}

// ConsumeLaunch atomically consumes a single-use launch capability.
func (c *ControlPlaneClient) ConsumeLaunch(ctx context.Context, launchToken string) (*LaunchResponse, error) {
	reqBody, err := json.Marshal(map[string]string{
		"launch_token": launchToken,
		"gateway_id":   c.GatewayID,
	})
	if err != nil {
		return nil, err
	}

	resp, bodyBytes, err := c.doRequest(ctx, "POST", "/internal/v1/launches/consume", reqBody)
	if err != nil {
		return nil, fmt.Errorf("control plane connection error: %w", err)
	}

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("consume launch failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var raw struct {
		SessionID       string `json:"session_id"`
		GrantID         string `json:"grant_id"`
		TargetAccountID string `json:"target_account_id"`
		CredentialType  string `json:"credential_type"`
		TargetHost      string `json:"target_host"`
		TargetPort      int    `json:"target_port"`
		TargetUsername  string `json:"target_username"`
		LeaseDeadline   string `json:"lease_deadline"`
		GrantExpiry     string `json:"grant_expiry"`
	}
	if err := json.Unmarshal(bodyBytes, &raw); err != nil {
		return nil, fmt.Errorf("failed to parse launch response: %w", err)
	}

	leaseDeadline, err := time.Parse(time.RFC3339, raw.LeaseDeadline)
	if err != nil {
		return nil, fmt.Errorf("invalid lease deadline timestamp: %w", err)
	}
	grantExpiry, err := time.Parse(time.RFC3339, raw.GrantExpiry)
	if err != nil {
		return nil, fmt.Errorf("invalid grant expiry timestamp: %w", err)
	}

	return &LaunchResponse{
		SessionID:       raw.SessionID,
		GrantID:         raw.GrantID,
		TargetAccountID: raw.TargetAccountID,
		CredentialType:  raw.CredentialType,
		TargetHost:      raw.TargetHost,
		TargetPort:      raw.TargetPort,
		TargetUsername:  raw.TargetUsername,
		LeaseDeadline:   leaseDeadline,
		GrantExpiry:     grantExpiry,
	}, nil
}

// RenewLease checks current grant status and extends the bounded lease deadline.
func (c *ControlPlaneClient) RenewLease(ctx context.Context, sessionID string) (*RenewResponse, error) {
	resp, bodyBytes, err := c.doRequest(ctx, "POST", fmt.Sprintf("/internal/v1/sessions/%s/renew", sessionID), nil)
	if err != nil {
		return nil, fmt.Errorf("renewal connection failure: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("lease renewal rejected with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var raw struct {
		SessionID     string `json:"session_id"`
		LeaseDeadline string `json:"lease_deadline"`
		GrantExpiry   string `json:"grant_expiry"`
	}
	if err := json.Unmarshal(bodyBytes, &raw); err != nil {
		return nil, fmt.Errorf("failed to parse renewal response: %w", err)
	}

	deadline, err := time.Parse(time.RFC3339, raw.LeaseDeadline)
	if err != nil {
		return nil, err
	}
	expiry, err := time.Parse(time.RFC3339, raw.GrantExpiry)
	if err != nil {
		return nil, err
	}

	return &RenewResponse{
		SessionID:     raw.SessionID,
		LeaseDeadline: deadline,
		GrantExpiry:   expiry,
	}, nil
}

// RecordingPayload carries terminal recording metadata for evidence ingestion.
type RecordingPayload struct {
	RecordingID     string `json:"recording_id,omitempty"`
	DigestSHA256    string `json:"digest_sha256"`
	StorageURI      string `json:"storage_uri"`
	SizeBytes       int    `json:"size_bytes"`
	DurationSeconds int    `json:"duration_seconds"`
	CoverageStatus  string `json:"coverage_status"`
}

// SendEvent reports session lifecycle events to the control plane.
func (c *ControlPlaneClient) SendEvent(ctx context.Context, sessionID, state, reason string) error {
	return c.SendEventWithRecording(ctx, sessionID, state, reason, nil)
}

// SendEventWithRecording reports session lifecycle events along with recording integrity metadata.
func (c *ControlPlaneClient) SendEventWithRecording(ctx context.Context, sessionID, state, reason string, rec *RecordingPayload) error {
	payload := map[string]interface{}{
		"state":     state,
		"reason":    reason,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	if rec != nil {
		payload["recording"] = rec
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	resp, _, err := c.doRequest(ctx, "POST", fmt.Sprintf("/internal/v1/sessions/%s/events", sessionID), bodyBytes)
	if err != nil {
		return fmt.Errorf("event delivery failure: %w", err)
	}

	if resp.StatusCode != http.StatusAccepted && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("gateway event delivery rejected with status %d", resp.StatusCode)
	}
	return nil
}

// VaultSecretResponse contains the decrypted secret returned from the control plane.
type VaultSecretResponse struct {
	CredentialType string `json:"credential_type"`
	SecretValue    string `json:"secret_value"`
	Username       string `json:"username"`
}

// RetrieveVaultSecret retrieves a vault-backed credential for target connection injection (P4-03).
func (c *ControlPlaneClient) RetrieveVaultSecret(ctx context.Context, grantID, sessionID, targetAccountID string) (*VaultSecretResponse, error) {
	reqBody, err := json.Marshal(map[string]string{
		"grant_id":          grantID,
		"session_id":        sessionID,
		"target_account_id": targetAccountID,
	})
	if err != nil {
		return nil, err
	}

	resp, bodyBytes, err := c.doRequest(ctx, "POST", "/internal/v1/credentials/vault-secret", reqBody)
	if err != nil {
		return nil, fmt.Errorf("control plane connection error: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("vault secret retrieval rejected (status %d): %s", resp.StatusCode, string(bodyBytes))
	}

	var secretResp VaultSecretResponse
	if err := json.Unmarshal(bodyBytes, &secretResp); err != nil {
		return nil, fmt.Errorf("failed to decode vault secret response: %w", err)
	}
	return &secretResp, nil
}

// RDPTunnelResponse contains the compiled connection parameters and security policies for RDP sessions.
type RDPTunnelResponse struct {
	SessionID               string `json:"session_id"`
	GrantID                 string `json:"grant_id"`
	TunnelToken             string `json:"tunnel_token,omitempty"`
	Protocol                string `json:"protocol"`
	Hostname                string `json:"hostname"`
	Port                    int    `json:"port"`
	Username                string `json:"username"`
	Password                string `json:"password"`
	Security                string `json:"security"`
	DisableClipboard        bool   `json:"disable_clipboard"`
	DisableDriveRedirection bool   `json:"disable_drive_redirection"`
	DisableAudio            bool   `json:"disable_audio"`
	DisablePrinting         bool   `json:"disable_printing"`
	EnableRecording         bool   `json:"enable_recording"`
	RecordingName           string `json:"recording_name"`
	LeaseDeadline           string `json:"lease_deadline"`
}

// CompileRDPTunnelParameters requests compiled RDP parameters with injected credentials from the control plane (P6-01).
func (c *ControlPlaneClient) CompileRDPTunnelParameters(ctx context.Context, grantID, sessionID string) (*RDPTunnelResponse, error) {
	reqBody, err := json.Marshal(map[string]string{
		"grant_id":   grantID,
		"session_id": sessionID,
	})
	if err != nil {
		return nil, err
	}

	resp, bodyBytes, err := c.doRequest(ctx, "POST", "/internal/v1/rdp/tunnel-parameters", reqBody)
	if err != nil {
		return nil, fmt.Errorf("control plane connection error: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("RDP tunnel compilation rejected (status %d): %s", resp.StatusCode, string(bodyBytes))
	}

	var tunnelResp RDPTunnelResponse
	if err := json.Unmarshal(bodyBytes, &tunnelResp); err != nil {
		return nil, fmt.Errorf("failed to decode RDP tunnel response: %w", err)
	}
	return &tunnelResp, nil
}
