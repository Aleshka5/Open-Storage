// Package chat answers one question about the resume as a Server-Sent Events
// stream, using the llm client. The handler is the gateway's own: it replaces
// the direct proxy to the model only because the prompt and the node map must
// not live in a YAML file.
//
// Nothing is stored between requests — no history, no session state — so the
// stream is the whole conversation.
package chat

import (
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"

	"github.com/aleshka5/open-storage/auth-gateway/internal/llm"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

// sessionHeader carries the SPA's per-browser-session id. It is opaque
// attribution for the proxy's logs, never a credential — the route is `public`,
// so nothing is authorized on it. A signed-in reader is identified by the
// verified cookie instead, which the edge has already turned into an identity.
const sessionHeader = "X-Chat-Session"

const maxBody = 4 << 10

type request struct {
	Question string `json:"question"`
}

type Handler struct {
	client *llm.Client
	log    *slog.Logger
}

// New returns the handler. A nil client is a 503, not a startup error: the chat
// is not load-bearing for sign-in.
func New(client *llm.Client, logger *slog.Logger) *Handler {
	if logger == nil {
		logger = slog.Default()
	}
	return &Handler{client: client, log: logger}
}

// ServeHTTP answers one question as a stream. Each request stands alone.
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if h.client == nil {
		h.log.Warn("chat_not_configured")
		writeError(w, http.StatusServiceUnavailable, "chat is not configured")
		return
	}

	var body request
	if err := json.NewDecoder(io.LimitReader(r.Body, maxBody)).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	question, err := llm.ValidateQuestion(body.Question)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming unsupported")
		return
	}

	hdr := w.Header()
	hdr.Set("Content-Type", "text/event-stream")
	hdr.Set("Cache-Control", "no-cache, no-transform")
	hdr.Set("Connection", "keep-alive")
	// Any buffering hop between here and the reader gets told not to hold it.
	hdr.Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	meta := metaOf(r)
	h.log.Info("chat_question", "session_id", meta.SessionID, "user_id", meta.UserID, "chars", len([]rune(question)))

	sendErr := h.client.Ask(r.Context(), question, meta, func(delta string) error {
		if err := writeSSE(w, map[string]string{"delta": delta}); err != nil {
			return err
		}
		flusher.Flush()
		return nil
	})
	if sendErr != nil {
		if errors.Is(sendErr, r.Context().Err()) {
			// The reader navigated away mid-answer; nothing left to write to.
			return
		}
		h.log.Error("chat_stream", "err", sendErr, "session_id", meta.SessionID)
		// The status line is long gone, so the failure travels as an event.
		_ = writeSSE(w, map[string]string{"error": "The owl could not reach its brain. Try again."})
		flusher.Flush()
		return
	}

	_, _ = io.WriteString(w, "data: [DONE]\n\n")
	flusher.Flush()
}

func writeSSE(w io.Writer, event map[string]string) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	_, err = w.Write(append(append([]byte("data: "), payload...), '\n', '\n'))
	return err
}

func writeError(w http.ResponseWriter, status int, value string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(`{"error":"` + value + `"}`))
}

// metaOf reads the verified identity the edge put on the request, plus the
// client's opaque session id.
func metaOf(r *http.Request) llm.Meta {
	m := llm.Meta{SessionID: sessionID(r)}
	if id := oidc.FromContext(r.Context()); id != nil {
		m.UserID = id.Subject
		m.Email = id.Email
	}
	return m
}

// sessionID keeps the client's id only when it is a short opaque token, so a
// caller cannot smuggle arbitrary text into the proxy's logs.
func sessionID(r *http.Request) string {
	raw := strings.TrimSpace(r.Header.Get(sessionHeader))
	if raw == "" || len(raw) > 64 {
		return uuid.NewString()
	}
	for _, c := range raw {
		switch {
		case c >= 'a' && c <= 'z', c >= 'A' && c <= 'Z', c >= '0' && c <= '9':
		case c == '-', c == '_', c == '.':
		default:
			return uuid.NewString()
		}
	}
	return raw
}
