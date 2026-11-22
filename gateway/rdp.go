package gateway

import (
	"context"
	"io"
	"log"
	"sync"
	"time"
)

// ActiveRDPSession represents an interactive RDP proxy tunnel managed by the gateway (P6-01, P6-02, ADR-012).
type ActiveRDPSession struct {
	SessionID     string
	GrantID       string
	ClientConn    io.ReadWriteCloser
	TargetConn    io.ReadWriteCloser
	CPClient      *ControlPlaneClient
	TunnelParams  *RDPTunnelResponse
	Recorder      *SessionRecorder
	LeaseDeadline time.Time
	GrantExpiry   time.Time

	cancelCtx  context.Context
	cancelFunc context.CancelFunc
	closeOnce  sync.Once
	notifyOnce sync.Once
}

// NewActiveRDPSession initializes an active RDP proxy session.
func NewActiveRDPSession(
	ctx context.Context,
	sessionID, grantID string,
	clientConn, targetConn io.ReadWriteCloser,
	cpClient *ControlPlaneClient,
	tunnelParams *RDPTunnelResponse,
	leaseDeadline, grantExpiry time.Time,
) *ActiveRDPSession {
	cancelCtx, cancelFunc := context.WithCancel(ctx)
	sess := &ActiveRDPSession{
		SessionID:     sessionID,
		GrantID:       grantID,
		ClientConn:    clientConn,
		TargetConn:    targetConn,
		CPClient:      cpClient,
		TunnelParams:  tunnelParams,
		LeaseDeadline: leaseDeadline,
		GrantExpiry:   grantExpiry,
		cancelCtx:     cancelCtx,
		cancelFunc:    cancelFunc,
	}

	// Default graphic / frame stream recorder
	sess.Recorder = NewSessionRecorder(
		sessionID,
		NewMemoryRecordingSink(),
		10*1024*1024,   // 10MB buffer
		30*time.Second, // 30s grace period
		func(reason string) {
			sess.Close(reason)
		},
	)
	return sess
}

// SetRecorder configures a custom recording sink or buffer.
func (s *ActiveRDPSession) SetRecorder(r *SessionRecorder) {
	s.Recorder = r
	if s.Recorder != nil && s.Recorder.OnTimeout == nil {
		s.Recorder.OnTimeout = func(reason string) {
			s.Close(reason)
		}
	}
}

func (s *ActiveRDPSession) notifyCaptureLoss() {
	s.notifyOnce.Do(func() {
		if s.ClientConn != nil {
			alert := "\r\n[SECURITY ALERT: RDP session recording pipeline interrupted. Forwarding paused. Session will terminate in 30s if not restored.]\r\n"
			_, _ = s.ClientConn.Write([]byte(alert))
		}
	})
}

// Run manages the bi-directional RDP stream proxying, bounded lease watcher, and recording capture.
func (s *ActiveRDPSession) Run() error {
	defer s.Close("RDP session closed by user or target disconnect")

	if s.Recorder == nil {
		s.Recorder = NewSessionRecorder(s.SessionID, NewMemoryRecordingSink(), 10*1024*1024, 30*time.Second, func(reason string) {
			s.Close(reason)
		})
	}

	go s.leaseWatcher()

	var wg sync.WaitGroup
	wg.Add(2)

	// User input (Client -> Target: mouse, keyboard, controls)
	go func() {
		defer wg.Done()
		buf := make([]byte, 4096)
		for {
			select {
			case <-s.cancelCtx.Done():
				return
			default:
				if s.ClientConn == nil || s.TargetConn == nil {
					return
				}
				n, err := s.ClientConn.Read(buf)
				if err != nil {
					s.cancelFunc()
					return
				}
				if n > 0 {
					chunk := buf[:n]
					if err := s.Recorder.RecordChunk(chunk); err != nil {
						s.notifyCaptureLoss()
						if err == ErrRecordingBufferFull {
							time.Sleep(100 * time.Millisecond)
							continue
						}
					}
					if _, err := s.TargetConn.Write(chunk); err != nil {
						s.cancelFunc()
						return
					}
				}
			}
		}
	}()

	// Graphic / Display output (Target -> Client)
	go func() {
		defer wg.Done()
		buf := make([]byte, 8192)
		for {
			select {
			case <-s.cancelCtx.Done():
				return
			default:
				if s.TargetConn == nil || s.ClientConn == nil {
					return
				}
				n, err := s.TargetConn.Read(buf)
				if err != nil {
					s.cancelFunc()
					return
				}
				if n > 0 {
					chunk := buf[:n]
					if err := s.Recorder.RecordChunk(chunk); err != nil {
						s.notifyCaptureLoss()
						if err == ErrRecordingBufferFull {
							time.Sleep(100 * time.Millisecond)
							continue
						}
					}
					if _, err := s.ClientConn.Write(chunk); err != nil {
						s.cancelFunc()
						return
					}
				}
			}
		}
	}()

	<-s.cancelCtx.Done()
	wg.Wait()
	return nil
}

// leaseWatcher monitors grant/lease deadlines and renews active RDP lease.
func (s *ActiveRDPSession) leaseWatcher() {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-s.cancelCtx.Done():
			return
		case now := <-ticker.C:
			earliestDeadline := s.LeaseDeadline
			if s.GrantExpiry.Before(earliestDeadline) {
				earliestDeadline = s.GrantExpiry
			}

			if now.After(earliestDeadline) || now.Equal(earliestDeadline) {
				log.Printf("[RDP Session %s] Lease/Grant expired at %s. Terminating connection.", s.SessionID, earliestDeadline)
				s.Close("Lease or grant expiration")
				return
			}

			remaining := time.Until(s.LeaseDeadline)
			if remaining < 60*time.Second {
				renewCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				resp, err := s.CPClient.RenewLease(renewCtx, s.SessionID)
				cancel()

				if err != nil {
					log.Printf("[RDP Session %s] Lease renewal failed: %v", s.SessionID, err)
					s.Close("Lease renewal failure or grant revocation")
					return
				} else {
					s.LeaseDeadline = resp.LeaseDeadline
					s.GrantExpiry = resp.GrantExpiry
				}
			}
		}
	}
}

// Close terminates connection in both directions and reports termination event to control plane.
func (s *ActiveRDPSession) Close(reason string) {
	s.closeOnce.Do(func() {
		s.cancelFunc()
		if s.ClientConn != nil {
			_ = s.ClientConn.Close()
		}
		if s.TargetConn != nil {
			_ = s.TargetConn.Close()
		}

		var recSummary *RecordingPayload
		if s.Recorder != nil {
			_ = s.Recorder.Close()
			recSummary = s.Recorder.GetSummary()
		}

		if s.CPClient != nil {
			eventCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = s.CPClient.SendEventWithRecording(eventCtx, s.SessionID, "ended", reason, recSummary)
		}
	})
}
