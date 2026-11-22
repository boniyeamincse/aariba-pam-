package gateway

import (
	"context"
	"io"
	"log"
	"sync"
	"time"

	"golang.org/x/crypto/ssh"
)

// ActiveSession represents an interactive terminal session through the gateway.
type ActiveSession struct {
	SessionID     string
	GrantID       string
	ClientChannel ssh.Channel
	TargetChannel ssh.Channel
	TargetClient  *ssh.Client
	CPClient      *ControlPlaneClient
	LeaseDeadline time.Time
	GrantExpiry   time.Time

	cancelCtx  context.Context
	cancelFunc context.CancelFunc
	closeOnce  sync.Once
}

// NewActiveSession initializes an active gateway session.
func NewActiveSession(
	ctx context.Context,
	sessionID, grantID string,
	clientChan, targetChan ssh.Channel,
	targetClient *ssh.Client,
	cpClient *ControlPlaneClient,
	leaseDeadline, grantExpiry time.Time,
) *ActiveSession {
	cancelCtx, cancelFunc := context.WithCancel(ctx)
	return &ActiveSession{
		SessionID:     sessionID,
		GrantID:       grantID,
		ClientChannel: clientChan,
		TargetChannel: targetChan,
		TargetClient:  targetClient,
		CPClient:      cpClient,
		LeaseDeadline: leaseDeadline,
		GrantExpiry:   grantExpiry,
		cancelCtx:     cancelCtx,
		cancelFunc:    cancelFunc,
	}
}

// Run manages the bi-directional proxying and bounded lease watcher.
func (s *ActiveSession) Run() error {
	defer s.Close("Session closed by user or target disconnect")

	// Start lease renewal goroutine
	go s.leaseWatcher()

	// Bi-directional stream copying
	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		_, _ = io.Copy(s.TargetChannel, s.ClientChannel)
		s.cancelFunc()
	}()

	go func() {
		defer wg.Done()
		_, _ = io.Copy(s.ClientChannel, s.TargetChannel)
		s.cancelFunc()
	}()

	// Wait for disconnection or lease expiry
	<-s.cancelCtx.Done()
	wg.Wait()

	return nil
}

// leaseWatcher monitors grant and lease deadlines and periodically renews active lease.
func (s *ActiveSession) leaseWatcher() {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-s.cancelCtx.Done():
			return
		case now := <-ticker.C:
			// 1. Check local expiry (earlier of lease deadline or grant expiry)
			earliestDeadline := s.LeaseDeadline
			if s.GrantExpiry.Before(earliestDeadline) {
				earliestDeadline = s.GrantExpiry
			}

			if now.After(earliestDeadline) || now.Equal(earliestDeadline) {
				log.Printf("[Session %s] Lease/Grant expired at %s. Terminating connection.", s.SessionID, earliestDeadline)
				s.Close("Lease or grant expiration")
				return
			}

			// 2. If less than half of lease remains, attempt renewal
			remaining := time.Until(s.LeaseDeadline)
			if remaining < 60*time.Second {
				renewCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				resp, err := s.CPClient.RenewLease(renewCtx, s.SessionID)
				cancel()

				if err != nil {
					log.Printf("[Session %s] Lease renewal failed: %v", s.SessionID, err)
					// If renewal rejected (e.g. revoked or expired), terminate promptly
					if now.Add(10 * time.Second).After(s.LeaseDeadline) {
						s.Close("Lease renewal failure or grant revocation")
						return
					}
				} else {
					s.LeaseDeadline = resp.LeaseDeadline
					s.GrantExpiry = resp.GrantExpiry
				}
			}
		}
	}
}

// Close terminates connection in both directions and reports termination event to control plane.
func (s *ActiveSession) Close(reason string) {
	s.closeOnce.Do(func() {
		s.cancelFunc()
		if s.ClientChannel != nil {
			_ = s.ClientChannel.Close()
		}
		if s.TargetChannel != nil {
			_ = s.TargetChannel.Close()
		}
		if s.TargetClient != nil {
			_ = s.TargetClient.Close()
		}

		// Report event to control plane
		if s.CPClient != nil {
			eventCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = s.CPClient.SendEvent(eventCtx, s.SessionID, "ended", reason)
		}
	})
}
