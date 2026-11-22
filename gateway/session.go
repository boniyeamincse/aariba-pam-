package gateway

import (
	"context"
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
	Recorder      *SessionRecorder
	LeaseDeadline time.Time
	GrantExpiry   time.Time

	cancelCtx  context.Context
	cancelFunc context.CancelFunc
	closeOnce  sync.Once
	notifyOnce sync.Once
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
	sess := &ActiveSession{
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

	// Default session recorder
	sess.Recorder = NewSessionRecorder(
		sessionID,
		NewMemoryRecordingSink(),
		10*1024*1024,
		30*time.Second,
		func(reason string) {
			sess.Close(reason)
		},
	)
	return sess
}

// SetRecorder overrides the active recorder with custom sink or buffer size.
func (s *ActiveSession) SetRecorder(r *SessionRecorder) {
	s.Recorder = r
	if s.Recorder != nil && s.Recorder.OnTimeout == nil {
		s.Recorder.OnTimeout = func(reason string) {
			s.Close(reason)
		}
	}
}

func (s *ActiveSession) notifyCaptureLoss() {
	s.notifyOnce.Do(func() {
		if s.ClientChannel != nil {
			alert := "\r\n\x1b[31;1m[SECURITY ALERT: Session recording pipeline interrupted. Forwarding paused. Session will terminate in 30s if not restored.]\x1b[0m\r\n"
			_, _ = s.ClientChannel.Write([]byte(alert))
		}
	})
}

// Run manages the bi-directional proxying and bounded lease watcher with recording interception.
func (s *ActiveSession) Run() error {
	defer s.Close("Session closed by user or target disconnect")

	// Ensure recorder exists
	if s.Recorder == nil {
		s.Recorder = NewSessionRecorder(s.SessionID, NewMemoryRecordingSink(), 10*1024*1024, 30*time.Second, func(reason string) {
			s.Close(reason)
		})
	}

	// Start lease renewal goroutine
	go s.leaseWatcher()

	// Bi-directional stream copying with recording interception
	var wg sync.WaitGroup
	wg.Add(2)

	// User input (Client -> Target)
	go func() {
		defer wg.Done()
		buf := make([]byte, 4096)
		for {
			select {
			case <-s.cancelCtx.Done():
				return
			default:
				if s.ClientChannel == nil || s.TargetChannel == nil {
					return
				}
				n, err := s.ClientChannel.Read(buf)
				if err != nil {
					s.cancelFunc()
					return
				}
				if n > 0 {
					chunk := buf[:n]
					if err := s.Recorder.RecordChunk(chunk); err != nil {
						s.notifyCaptureLoss()
						if err == ErrRecordingBufferFull {
							time.Sleep(200 * time.Millisecond)
							continue
						}
					}
					if _, err := s.TargetChannel.Write(chunk); err != nil {
						s.cancelFunc()
						return
					}
				}
			}
		}
	}()

	// Terminal output (Target -> Client)
	go func() {
		defer wg.Done()
		buf := make([]byte, 4096)
		for {
			select {
			case <-s.cancelCtx.Done():
				return
			default:
				if s.TargetChannel == nil || s.ClientChannel == nil {
					return
				}
				n, err := s.TargetChannel.Read(buf)
				if err != nil {
					s.cancelFunc()
					return
				}
				if n > 0 {
					chunk := buf[:n]
					if err := s.Recorder.RecordChunk(chunk); err != nil {
						s.notifyCaptureLoss()
						if err == ErrRecordingBufferFull {
							time.Sleep(200 * time.Millisecond)
							continue
						}
					}
					if _, err := s.ClientChannel.Write(chunk); err != nil {
						s.cancelFunc()
						return
					}
				}
			}
		}
	}()

	// Wait for disconnection, lease expiry, or capture loss timeout
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

// Close terminates connection in both directions and reports termination event with recording summary to control plane.
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

		// Close recorder and get final summary
		var recSummary *RecordingPayload
		if s.Recorder != nil {
			_ = s.Recorder.Close()
			recSummary = s.Recorder.GetSummary()
		}

		// Report event with recording metadata to control plane
		if s.CPClient != nil {
			eventCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = s.CPClient.SendEventWithRecording(eventCtx, s.SessionID, "ended", reason, recSummary)
		}
	})
}
