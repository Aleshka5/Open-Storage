package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"strings"

	"github.com/aleshka5/open-storage/auth-gateway/internal/chat"
	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/llm"
	"github.com/aleshka5/open-storage/auth-gateway/internal/tracing"
)

// newChat builds POST /api/chat, or a handler that answers 503, from the `llm`
// block and the environment. It never fails the start: the owl is the page's
// mascot, not its login.
//
// Env, all optional:
//
//	LLM_HOST, LLM_MODEL, LLM_REASONING_EFFORT  fall back to `llm.*` in the config
//	LLM_API_KEY                                the key, or `env:LLM_API_KEY` in the config
//	MLFLOW_TRACING_ENDPOINT, MLFLOW_EXPERIMENT_ID  OTLP traces; unset means none
func newChat(ctx context.Context, file *config.File, l *slog.Logger) (http.Handler, tracing.Shutdown, error) {
	noShutdown := func(context.Context) error { return nil }

	cfg := llm.Config{
		Host:            firstNonEmpty(os.Getenv("LLM_HOST"), file.LLM.Host),
		APIKey:          file.Secrets().LLMAPIKey,
		Model:           firstNonEmpty(os.Getenv("LLM_MODEL"), file.LLM.Model),
		ReasoningEffort: firstNonEmpty(os.Getenv("LLM_REASONING_EFFORT"), file.LLM.ReasoningEffort),
		Timeout:         file.LLM.Timeout.D(),
	}

	tracer, shutdown, err := tracing.New(ctx, tracing.Config{
		Endpoint:     strings.TrimSpace(os.Getenv("MLFLOW_TRACING_ENDPOINT")),
		ExperimentID: strings.TrimSpace(os.Getenv("MLFLOW_EXPERIMENT_ID")),
		ServiceName:  "auth-gateway",
	})
	if err != nil {
		// Tracing is a record of an answer, never a condition of one.
		l.Warn("tracing_disabled", "err", err)
		shutdown = noShutdown
	}
	cfg.Tracer = tracer

	client, err := llm.New(cfg)
	if err != nil {
		// A route that asks for `chat: true` still answers, with 503, and says
		// why in the log.
		l.Warn("chat_disabled", "err", err)
		return chat.New(nil, l), shutdown, nil
	}
	l.Info("chat_enabled", "model", cfg.Model, "reasoning_effort", cfg.ReasoningEffort, "host_set", cfg.Host != "", "key_set", cfg.APIKey != "")
	return chat.New(client, l), shutdown, nil
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if s := strings.TrimSpace(v); s != "" {
			return s
		}
	}
	return ""
}
