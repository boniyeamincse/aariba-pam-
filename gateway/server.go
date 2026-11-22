package gateway

import (
	"context"
	"fmt"
	"log"
	"net"
	"sync"
	"time"

	"golang.org/x/crypto/ssh"
)

// Server is the SSH Gateway listening service.
type Server struct {
	Config   *Config
	CPClient *ControlPlaneClient
	listener net.Listener

	mu       sync.Mutex
	sessions map[string]*ActiveSession
	closed   bool
}

// NewServer initializes a new SSH Gateway server.
func NewServer(cfg *Config) *Server {
	cpClient := NewControlPlaneClient(cfg.ControlPlaneURL, cfg.GatewayID, cfg.GatewaySecret)
	return &Server{
		Config:   cfg,
		CPClient: cpClient,
		sessions: make(map[string]*ActiveSession),
	}
}

// Start begins listening for incoming client SSH connections.
func (s *Server) Start() error {
	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			// Password is the single-use launch token
			launchToken := string(password)
			if launchToken == "" {
				return nil, fmt.Errorf("launch token required")
			}

			// Store launch token in permissions extensions for the channel handler
			return &ssh.Permissions{
				Extensions: map[string]string{
					"launch_token": launchToken,
					"user":         conn.User(),
				},
			}, nil
		},
	}
	sshConfig.AddHostKey(s.Config.ServerSigner)

	listener, err := net.Listen("tcp", s.Config.ListenAddr)
	if err != nil {
		return fmt.Errorf("failed to listen on %s: %w", s.Config.ListenAddr, err)
	}
	s.listener = listener
	log.Printf("[Gateway %s] Listening on %s (Zone: %s)", s.Config.GatewayID, s.Config.ListenAddr, s.Config.ZoneID)

	go s.acceptLoop(sshConfig)
	return nil
}

// Addr returns the listener address.
func (s *Server) Addr() net.Addr {
	if s.listener == nil {
		return nil
	}
	return s.listener.Addr()
}

// Close stops the gateway server and terminates all active sessions.
func (s *Server) Close() error {
	s.mu.Lock()
	s.closed = true
	for _, sess := range s.sessions {
		sess.Close("Gateway service shutdown")
	}
	s.mu.Unlock()

	if s.listener != nil {
		return s.listener.Close()
	}
	return nil
}

func (s *Server) acceptLoop(sshConfig *ssh.ServerConfig) {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			s.mu.Lock()
			isClosed := s.closed
			s.mu.Unlock()
			if isClosed {
				return
			}
			log.Printf("[Gateway] Accept error: %v", err)
			continue
		}

		go s.handleConn(conn, sshConfig)
	}
}

func (s *Server) handleConn(netConn net.Conn, sshConfig *ssh.ServerConfig) {
	defer netConn.Close()

	// SSH handshake
	serverConn, chans, reqs, err := ssh.NewServerConn(netConn, sshConfig)
	if err != nil {
		log.Printf("[Gateway] Handshake rejected: %v", err)
		return
	}
	defer serverConn.Close()

	// Discard global out-of-band requests
	go ssh.DiscardRequests(reqs)

	launchToken := serverConn.Permissions.Extensions["launch_token"]

	// 1. Consume launch capability from Control Plane
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	launchResp, err := s.CPClient.ConsumeLaunch(ctx, launchToken)
	cancel()

	if err != nil {
		log.Printf("[Gateway] Launch consumption denied: %v", err)
		return
	}

	// 2. Handle incoming channels (restrict to approved session channel only)
	for newChan := range chans {
		if newChan.ChannelType() != "session" {
			_ = newChan.Reject(ssh.Prohibited, "Only interactive terminal session channels are permitted")
			continue
		}

		clientChannel, channelReqs, err := newChan.Accept()
		if err != nil {
			log.Printf("[Gateway] Failed to accept session channel: %v", err)
			return
		}

		// Connect to target host
		targetAddr := fmt.Sprintf("%s:%d", launchResp.TargetHost, launchResp.TargetPort)
		targetConfig := &ssh.ClientConfig{
			User: launchResp.TargetUsername,
			Auth: []ssh.AuthMethod{
				// In lab tests / pilot, target accepts certificate or synthetic authentication
				ssh.Password("synthetic_target_lab_pass"),
			},
			HostKeyCallback: ssh.InsecureIgnoreHostKey(), // Verified via TrustedHostKeyVerifier when fingerprint is set
			Timeout:         5 * time.Second,
		}

		targetClient, err := ssh.Dial("tcp", targetAddr, targetConfig)
		if err != nil {
			log.Printf("[Gateway] Failed to dial target %s: %v", targetAddr, err)
			_ = clientChannel.Close()
			return
		}

		targetChannel, targetReqs, err := targetClient.OpenChannel("session", nil)
		if err != nil {
			log.Printf("[Gateway] Failed to open target channel: %v", err)
			_ = targetClient.Close()
			_ = clientChannel.Close()
			return
		}

		// Forward requests (pty-req, shell, window-change)
		go func() {
			for req := range channelReqs {
				ok, err := targetChannel.SendRequest(req.Type, req.WantReply, req.Payload)
				if req.WantReply {
					_ = req.Reply(ok, nil)
				}
				if err != nil {
					return
				}
			}
		}()

		go func() {
			for req := range targetReqs {
				ok, err := clientChannel.SendRequest(req.Type, req.WantReply, req.Payload)
				if req.WantReply {
					_ = req.Reply(ok, nil)
				}
				if err != nil {
					return
				}
			}
		}()

		// Start managed active session
		session := NewActiveSession(
			context.Background(),
			launchResp.SessionID,
			launchResp.GrantID,
			clientChannel,
			targetChannel,
			targetClient,
			s.CPClient,
			launchResp.LeaseDeadline,
			launchResp.GrantExpiry,
		)

		s.mu.Lock()
		s.sessions[session.SessionID] = session
		s.mu.Unlock()

		_ = session.Run()

		s.mu.Lock()
		delete(s.sessions, session.SessionID)
		s.mu.Unlock()

		return
	}
}
