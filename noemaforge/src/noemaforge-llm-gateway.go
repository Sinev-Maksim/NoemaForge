/*
=== NoemaForge File Header ===
File: noemaforge/src/noemaforge-llm-gateway.go
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
*/
// === NoemaForge Autodoc File Header ===
// File: src/noemaforge-llm-gateway.go
// Purpose: Provide the Go service or helper 'noemaforge-llm-gateway'.
// Invoked by: systemd/services, operator builds, or direct process startup.
// Inputs: environment variables, HTTP requests, and local Unix sockets as implemented below.
// Outputs: HTTP responses, log lines, and local socket side effects.
// AutoDoc: refreshed 2026-04-09 (heuristic)
// === End NoemaForge Autodoc File Header ===



package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var safeModelRe = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,80}$`)

// === NoemaForge Autodoc Function Header ===
// Function: autoBackend(model string -> (string, bool))
// Purpose: Provide the Go routine 'autoBackend'.
// Inputs:
//   - model string -> (string, bool)
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func autoBackend(model string) (string, bool) {
	m := strings.TrimSpace(model)
	if m == "" {
		return "", false
	}
	if !safeModelRe.MatchString(m) {
		return "", false
	}
	// Conservative: only allow the standard backend socket directory.
	sock := filepath.Join("/run/noemaforge/llm/backends", m+".sock")
	if st, err := os.Stat(sock); err == nil {
		// Ensure it's a socket-like filesystem entry.
		if (st.Mode() & os.ModeSocket) != 0 {
			return sock, true
		}
		// Some systems report unix sockets differently; accept existence as a fallback.
		return sock, true
	}
	return "", false
}

type cfg struct {
	ListenSock   string
	DefaultModel string
	Backends     map[string]string
	MaxBodyBytes int64
	ReadHdrTO    time.Duration
}

// === NoemaForge Autodoc Function Header ===
// Function: parseBackends(s string -> map[string]string)
// Purpose: Provide the Go routine 'parseBackends'.
// Inputs:
//   - s string -> map[string]string
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func parseBackends(s string) map[string]string {
	m := map[string]string{}
	s = strings.TrimSpace(s)
	if s == "" {
		return m
	}
	for _, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		kv := strings.SplitN(part, ":", 2)
		if len(kv) != 2 {
			continue
		}
		m[strings.TrimSpace(kv[0])] = strings.TrimSpace(kv[1])
	}
	return m
}

// === NoemaForge Autodoc Function Header ===
// Function: getenvDefault(name, def string -> string)
// Purpose: Provide the Go routine 'getenvDefault'.
// Inputs:
//   - name, def string -> string
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func getenvDefault(name, def string) string {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		return def
	}
	return v
}

// === NoemaForge Autodoc Function Header ===
// Function: getenvInt64(name string, def int64 -> int64)
// Purpose: Provide the Go routine 'getenvInt64'.
// Inputs:
//   - name string, def int64 -> int64
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func getenvInt64(name string, def int64) int64 {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		return def
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil || n <= 0 {
		return def
	}
	return n
}

// === NoemaForge Autodoc Function Header ===
// Function: main()
// Purpose: Provide the Go routine 'main'.
// Inputs:
//   - No explicit parameters.
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func main() {
	c := cfg{
		ListenSock:   getenvDefault("NOEMAFORGE_GATEWAY_SOCKET", "/run/noemaforge/llm/gateway.sock"),
		DefaultModel: getenvDefault("NOEMAFORGE_DEFAULT_MODEL", "main"),
		Backends:     parseBackends(os.Getenv("NOEMAFORGE_BACKENDS")),
		MaxBodyBytes: getenvInt64("NOEMAFORGE_MAX_BODY_BYTES", 10<<20), // 10 MiB
		ReadHdrTO:    10 * time.Second,
	}
	if len(c.Backends) == 0 {
		c.Backends = map[string]string{"main": "/run/noemaforge/llm/backends/main.sock"}
	}

	if err := os.MkdirAll(filepath.Dir(c.ListenSock), 0750); err != nil {
		log.Fatalf("mkdir: %v", err)
	}
	_ = os.Remove(c.ListenSock)

	l, err := net.Listen("unix", c.ListenSock)
	if err != nil {
		log.Fatalf("listen: %v", err)
	}
	_ = os.Chmod(c.ListenSock, 0660)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte("ok")) })
	mux.HandleFunc("/v1/health", func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte("ok")) })

	for _, p := range []string{"/v1/chat/completions", "/v1/completions", "/v1/embeddings"} {
		path := p
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
			handleProxy(c, w, r)
		})
	}

	srv := &http.Server{
		Handler:           logMiddleware(mux),
		ReadHeaderTimeout: c.ReadHdrTO,
	}
	log.Printf("noemaforge-llm-gateway listening on unix://%s", c.ListenSock)
	if err := srv.Serve(l); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("serve: %v", err)
	}
}

// === NoemaForge Autodoc Function Header ===
// Function: handleProxy(c cfg, w http.ResponseWriter, r *http.Request)
// Purpose: Provide the Go routine 'handleProxy'.
// Inputs:
//   - c cfg, w http.ResponseWriter, r *http.Request
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func handleProxy(c cfg, w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, c.MaxBodyBytes+1))
	if err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if int64(len(body)) > c.MaxBodyBytes {
		http.Error(w, "request too large", http.StatusRequestEntityTooLarge)
		return
	}

	var req map[string]any
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "invalid json", http.StatusBadRequest)
		return
	}
	model, _ := req["model"].(string)
	if strings.TrimSpace(model) == "" {
		model = c.DefaultModel
		req["model"] = model
		body, _ = json.Marshal(req)
	}

	backendSock, ok := c.Backends[model]
	if !ok {
		if sock, ok2 := autoBackend(model); ok2 {
			backendSock = sock
		} else {
			http.Error(w, "unknown model", http.StatusBadRequest)
			return
		}
	}

	resp, err := proxyUnix(r.Context(), backendSock, r.URL.Path, body, r.Header)
	if err != nil {
		http.Error(w, "backend unavailable", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	for k, vv := range resp.Header {
		if strings.EqualFold(k, "Connection") || strings.EqualFold(k, "Transfer-Encoding") {
			continue
		}
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

// === NoemaForge Autodoc Function Header ===
// Function: proxyUnix(ctx context.Context, sockPath, path string, body []byte, hdr http.Header -> (*http.Response, error))
// Purpose: Provide the Go routine 'proxyUnix'.
// Inputs:
//   - ctx context.Context, sockPath, path string, body []byte, hdr http.Header -> (*http.Response, error)
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func proxyUnix(ctx context.Context, sockPath, path string, body []byte, hdr http.Header) (*http.Response, error) {
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			var d net.Dialer
			return d.DialContext(ctx, "unix", sockPath)
		},
	}
	client := &http.Client{Transport: transport}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://unix"+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header = hdr.Clone()
	req.Header.Set("Content-Type", "application/json")
	req.Header.Del("Authorization") // do not forward secrets by default

	return client.Do(req)
}

// === NoemaForge Autodoc Function Header ===
// Function: logMiddleware(next http.Handler -> http.Handler)
// Purpose: Provide the Go routine 'logMiddleware'.
// Inputs:
//   - next http.Handler -> http.Handler
// Called by:
//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.
// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.
// === End NoemaForge Autodoc Function Header ===
func logMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		log.Printf("gw %s %s", r.Method, r.URL.Path)
		next.ServeHTTP(w, r)
	})
}
