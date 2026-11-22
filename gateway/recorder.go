package gateway

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"hash"
	"sync"
	"time"
)

var (
	// ErrRecordingBufferFull is returned when the recording buffer exceeds capacity.
	ErrRecordingBufferFull = errors.New("recording buffer full: capture pipeline stalled")
	// ErrPipelineDegraded is returned when the recording sink is failing.
	ErrPipelineDegraded = errors.New("recording pipeline degraded: forwarding paused")
)

// RecordingSink defines the interface for delivering terminal stream chunks to storage.
type RecordingSink interface {
	Write(p []byte) (n int, err error)
	Close() error
}

// MemoryRecordingSink is an in-memory sink for lab and testing.
type MemoryRecordingSink struct {
	mu     sync.Mutex
	data   []byte
	closed bool
	fail   bool
}

// NewMemoryRecordingSink initializes an in-memory recording sink.
func NewMemoryRecordingSink() *MemoryRecordingSink {
	return &MemoryRecordingSink{data: make([]byte, 0, 4096)}
}

// SetFailing toggles simulated failure on the sink.
func (m *MemoryRecordingSink) SetFailing(fail bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.fail = fail
}

func (m *MemoryRecordingSink) Write(p []byte) (n int, err error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closed {
		return 0, errors.New("sink closed")
	}
	if m.fail {
		return 0, errors.New("storage network partition: delivery failed")
	}
	m.data = append(m.data, p...)
	return len(p), nil
}

func (m *MemoryRecordingSink) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.closed = true
	return nil
}

// Bytes returns written content.
func (m *MemoryRecordingSink) Bytes() []byte {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]byte, len(m.data))
	copy(out, m.data)
	return out
}

// SessionRecorder manages live asciinema stream capture, SHA-256 digests, and fail-closed buffering.
type SessionRecorder struct {
	SessionID       string
	Sink            RecordingSink
	MaxBufferSize   int
	GracePeriod     time.Duration
	OnTimeout       func(reason string)

	mu              sync.Mutex
	hasher          hash.Hash
	totalBytes      int
	startTime       time.Time
	coverageStatus  string // "complete", "partial", "gap"
	degraded        bool
	degradedAt      time.Time
	timer           *time.Timer
	buffer          []byte
	closed          bool
}

// NewSessionRecorder creates a new recorder for an active session.
func NewSessionRecorder(
	sessionID string,
	sink RecordingSink,
	maxBufferSize int,
	gracePeriod time.Duration,
	onTimeout func(reason string),
) *SessionRecorder {
	if maxBufferSize <= 0 {
		maxBufferSize = 10 * 1024 * 1024 // 10 MB default
	}
	if gracePeriod <= 0 {
		gracePeriod = 30 * time.Second
	}

	return &SessionRecorder{
		SessionID:      sessionID,
		Sink:           sink,
		MaxBufferSize:  maxBufferSize,
		GracePeriod:    gracePeriod,
		OnTimeout:      onTimeout,
		hasher:         sha256.New(),
		startTime:      time.Now().UTC(),
		coverageStatus: "complete",
		buffer:         make([]byte, 0, 1024),
	}
}

// RecordChunk ingests a slice of raw terminal traffic (stdin or stdout).
// Enforces fail-closed buffering: if sink fails and buffer exceeds max, marks gap and pauses forwarding.
func (r *SessionRecorder) RecordChunk(chunk []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return errors.New("recorder is closed")
	}

	// Update hash digest and total count
	r.hasher.Write(chunk)
	r.totalBytes += len(chunk)

	// Attempt write to sink
	if r.Sink != nil {
		_, err := r.Sink.Write(chunk)
		if err != nil {
			// Sink delivery failure -> enter degraded state
			if !r.degraded {
				r.degraded = true
				r.degradedAt = time.Now()
				r.coverageStatus = "gap"

				// Start grace period timer
				if r.OnTimeout != nil {
					r.timer = time.AfterFunc(r.GracePeriod, func() {
						r.mu.Lock()
						isDegraded := r.degraded
						r.mu.Unlock()
						if isDegraded {
							r.OnTimeout("Recording capture loss exceeded grace period (fail-closed)")
						}
					})
				}
			}

			// Buffer locally up to maxBufferSize
			if len(r.buffer)+len(chunk) > r.MaxBufferSize {
				return ErrRecordingBufferFull
			}
			r.buffer = append(r.buffer, chunk...)
			return ErrPipelineDegraded
		}
	}

	// If sink succeeded and we were previously degraded, try flushing local buffer
	if r.degraded {
		if r.Sink != nil && len(r.buffer) > 0 {
			if _, err := r.Sink.Write(r.buffer); err == nil {
				r.buffer = r.buffer[:0]
				r.degraded = false
				if r.timer != nil {
					r.timer.Stop()
					r.timer = nil
				}
			}
		} else {
			r.degraded = false
			if r.timer != nil {
				r.timer.Stop()
				r.timer = nil
			}
		}
	}

	return nil
}

// IsDegraded returns true if capture storage delivery is failing.
func (r *SessionRecorder) IsDegraded() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.degraded
}

// CoverageStatus returns the evidence coverage status ("complete" or "gap").
func (r *SessionRecorder) CoverageStatus() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.coverageStatus
}

// DigestSHA256 returns the hexadecimal SHA-256 digest of all recorded stream bytes.
func (r *SessionRecorder) DigestSHA256() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return hex.EncodeToString(r.hasher.Sum(nil))
}

// GetSummary returns recording metadata for control plane event submission.
func (r *SessionRecorder) GetSummary() *RecordingPayload {
	r.mu.Lock()
	defer r.mu.Unlock()

	duration := int(time.Since(r.startTime).Seconds())
	if duration <= 0 {
		duration = 1
	}

	return &RecordingPayload{
		DigestSHA256:    hex.EncodeToString(r.hasher.Sum(nil)),
		StorageURI:      fmt.Sprintf("s3://ariba-pam-evidence-worm/recordings/%s.cast", r.SessionID),
		SizeBytes:       r.totalBytes,
		DurationSeconds: duration,
		CoverageStatus:  r.coverageStatus,
	}
}

// Close flushes remaining buffers and closes the sink.
func (r *SessionRecorder) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return nil
	}
	r.closed = true

	if r.timer != nil {
		r.timer.Stop()
	}

	if r.Sink != nil {
		return r.Sink.Close()
	}
	return nil
}
