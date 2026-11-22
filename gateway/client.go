package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// LaunchResponse contains the authorization details returned by the control plane.
type LaunchResponse struct {
	SessionID      string    `json:"session_id"`
	GrantID        string    `json:"grant_id"`
	TargetHost     string    `json:"target_host"`
	TargetPort     int       `json:"target_port"`
	TargetUsername string    `json:"target_username"`
	LeaseDeadline  time.Time `json:"lease_deadline"`
	GrantExpiry    time.Time `json:"grant_expiry"`
}

// RenewResponse contains the updated lease deadline from renewal.
type RenewResponse struct {
	SessionID     string    `json:"session_id"`
	LeaseDeadline time.Time `json:"lease_deadline"`
	GrantExpiry   time.Time `json:"grant_expiry"`
}

// ControlPlaneClient communicates with the Ariba PAM control plane.
type ControlPlaneClient struct {
	BaseURL    string
	GatewayID  string
	Secret     string
	HTTPClient *http.Client
}

// NewControlPlaneClient initializes a client for internal control plane routes.
func NewControlPlaneClient(baseURL, gatewayID, secret string) *ControlPlaneClient {
	return &ControlPlaneClient{
		BaseURL:   baseURL,
		GatewayID: gatewayID,
		Secret:    secret,
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
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

	req, err := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/internal/v1/launches/consume", bytes.NewReader(reqBody))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Secret", c.Secret)

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("control plane connection error: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("consume launch failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var raw struct {
		SessionID      string `json:"session_id"`
		GrantID        string `json:"grant_id"`
		TargetHost     string `json:"target_host"`
		TargetPort     int    `json:"target_port"`
		TargetUsername string `json:"target_username"`
		LeaseDeadline  string `json:"lease_deadline"`
		GrantExpiry    string `json:"grant_expiry"`
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
		SessionID:      raw.SessionID,
		GrantID:        raw.GrantID,
		TargetHost:     raw.TargetHost,
		TargetPort:     raw.TargetPort,
		TargetUsername: raw.TargetUsername,
		LeaseDeadline:  leaseDeadline,
		GrantExpiry:    grantExpiry,
	}, nil
}

// RenewLease checks current grant status and extends the bounded lease deadline.
func (c *ControlPlaneClient) RenewLease(ctx context.Context, sessionID string) (*RenewResponse, error) {
	req, err := http.NewRequestWithContext(ctx, "POST", fmt.Sprintf("%s/internal/v1/sessions/%s/renew", c.BaseURL, sessionID), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Gateway-Secret", c.Secret)

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("renewal connection failure: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)
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

	req, err := http.NewRequestWithContext(ctx, "POST", fmt.Sprintf("%s/internal/v1/sessions/%s/events", c.BaseURL, sessionID), bytes.NewReader(bodyBytes))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Secret", c.Secret)

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("event delivery failure: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("gateway event delivery rejected with status %d", resp.StatusCode)
	}
	return nil
}

