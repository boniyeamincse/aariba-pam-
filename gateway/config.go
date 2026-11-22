package gateway

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/pem"
	"time"

	"golang.org/x/crypto/ssh"
)

// Config defines the configuration parameters for the Ariba PAM SSH Gateway.
type Config struct {
	GatewayID            string
	ZoneID               string
	ControlPlaneURL      string
	GatewaySecret        string
	ListenAddr           string
	DefaultLeaseDuration time.Duration
	ServerSigner         ssh.Signer
}

// DefaultConfig generates a development/lab configuration with an ephemeral host key.
func DefaultConfig() (*Config, error) {
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, err
	}
	signer, err := ssh.NewSignerFromKey(priv)
	if err != nil {
		return nil, err
	}

	return &Config{
		GatewayID:            "gw_lab_01",
		ZoneID:               "zon_lab_01",
		ControlPlaneURL:      "http://localhost:8000",
		GatewaySecret:        "synthetic-gateway-shared-secret-lab",
		ListenAddr:           "127.0.0.1:2222",
		DefaultLeaseDuration: 5 * time.Minute,
		ServerSigner:         signer,
	}, nil
}

// GenerateSigner creates an Ed25519 signer for synthetic lab hosts.
func GenerateSigner() (ssh.Signer, error) {
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, err
	}
	return ssh.NewSignerFromKey(priv)
}

// GeneratePEMKey generates a PEM-encoded private key string for lab fixtures.
func GeneratePEMKey() (string, error) {
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return "", err
	}
	b, err := ssh.MarshalPrivateKey(priv, "")
	if err != nil {
		return "", err
	}
	return string(pem.EncodeToMemory(b)), nil
}
