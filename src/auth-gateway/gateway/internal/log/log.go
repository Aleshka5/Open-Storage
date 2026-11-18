// Package log configures the process logger. One JSON line per record, so the
// access log and the rest of the process read the same way in Loki.
package log

import (
	"log/slog"
	"os"
	"strings"
)

// New returns a JSON logger at the given level. An unknown level is info.
func New(level string) *slog.Logger {
	var l slog.Level
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "debug":
		l = slog.LevelDebug
	case "warn", "warning":
		l = slog.LevelWarn
	case "error":
		l = slog.LevelError
	default:
		l = slog.LevelInfo
	}
	return slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: l}))
}
