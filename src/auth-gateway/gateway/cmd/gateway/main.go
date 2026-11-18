// Command gateway is the whole edge: TLS is terminated in front of it, and it
// owns routing, policy, identity, the BFF and /admin. Configuration is read once
// at start; a change is a restart (ADR-0004).
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/adminapi"
	"github.com/aleshka5/open-storage/auth-gateway/internal/bff"
	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/edge"
	"github.com/aleshka5/open-storage/auth-gateway/internal/log"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

func main() {
	logger := log.New(os.Getenv("LOG_LEVEL"))
	if err := run(logger); err != nil {
		logger.Error("gateway_start_failed", "err", err)
		os.Exit(1)
	}
}

func run(l *slog.Logger) error {
	path := strings.TrimSpace(os.Getenv("GATEWAY_CONFIG"))
	if path == "" {
		return fmt.Errorf("GATEWAY_CONFIG is required")
	}
	file, err := config.Load(path)
	if err != nil {
		return err
	}
	if file.Admin.ClientID == "" {
		return fmt.Errorf("admin.client_id is required: /admin has no service account")
	}
	ctx := context.Background()
	// Keycloak takes tens of seconds to import a realm on an empty database. A
	// bounded wait keeps the first start from becoming a crash loop, and still
	// fails loudly when the idp is simply absent.
	provider, err := discoverWithRetry(ctx, file.IdP.Issuer, l)
	if err != nil {
		return err
	}
	verifier, err := oidc.NewVerifier(ctx, provider, file.IdP.Audience, file.IdP.AuthorizedParty, file.IdP.ClientID, file.IdP.JWKSTTL.D(), nil)
	if err != nil {
		return err
	}
	sealer, err := session.NewSealer(file.Secrets().SessionKey, file.Session.CookieDomain, file.Session.AccessTTL.D(), file.Session.IdleTTL.D())
	if err != nil {
		return err
	}
	admin, err := adminapi.New(adminapi.Config{
		BaseURL:      baseURL(file.IdP.Issuer),
		Realm:        realmOf(file.IdP.Issuer),
		ClientID:     file.Admin.ClientID,
		ClientSecret: file.Secrets().AdminClient,
		Services:     file.Services,
	})
	if err != nil {
		return err
	}
	srv, err := edge.New(edge.Config{
		File:     file,
		Verifier: verifier,
		Sealer:   sealer,
		Admin:    admin.Handler(),
		Logger:   l,
	})
	if err != nil {
		return err
	}
	auth, err := bff.New(bff.Config{
		File:     file,
		Provider: provider,
		Verifier: verifier,
		Sealer:   sealer,
		Logger:   l,
		Metrics:  srv.Counters(),
	})
	if err != nil {
		return err
	}
	srv.SetBFF(auth.Handler())
	srv.SetRefresher(auth)

	// Metrics live on their own listener so the public port cannot serve them.
	metricsAddr := strings.TrimSpace(os.Getenv("METRICS_ADDR"))
	if metricsAddr == "" {
		metricsAddr = ":9000"
	}
	metricsServer := &http.Server{
		Addr:              metricsAddr,
		Handler:           srv.MetricsHandler(),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       30 * time.Second,
	}
	go func() {
		if err := metricsServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			l.Error("metrics_listener_failed", "err", err)
		}
	}()

	httpServer := &http.Server{
		Addr:    file.Listen,
		Handler: srv.Handler(),
		// No ReadTimeout and no WriteTimeout: both cut long uploads, SSE and
		// WebSocket lifetimes. Only the header and idle waits are bounded.
		ReadHeaderTimeout: file.Defaults.Timeouts.ReadHeader.D(),
		IdleTimeout:       file.Defaults.Timeouts.Idle.D(),
	}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-stop
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		_ = metricsServer.Shutdown(shutdownCtx)
		_ = httpServer.Shutdown(shutdownCtx)
	}()
	l.Info("gateway_listening", "addr", file.Listen, "hosts", len(file.Hosts))
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func discoverWithRetry(ctx context.Context, issuer string, l *slog.Logger) (*oidc.Provider, error) {
	deadline := time.Now().Add(90 * time.Second)
	for {
		provider, err := oidc.Discover(ctx, issuer, nil)
		if err == nil {
			return provider, nil
		}
		if time.Now().After(deadline) {
			return nil, err
		}
		l.Warn("idp_not_ready", "err", err, "retry_in", "3s")
		time.Sleep(3 * time.Second)
	}
}

// baseURL drops the /realms/... suffix: the Admin API takes the issuer base.
func baseURL(issuer string) string {
	if i := strings.Index(issuer, "/realms/"); i > 0 {
		return issuer[:i]
	}
	return strings.TrimRight(issuer, "/")
}

func realmOf(issuer string) string {
	if i := strings.Index(issuer, "/realms/"); i >= 0 {
		return strings.Trim(strings.TrimRight(issuer[i:], "/")[len("/realms/"):], "/")
	}
	return "filenkov"
}
