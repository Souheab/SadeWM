PREFIX ?= /usr/local
BINDIR  = $(PREFIX)/bin
BINARY  = sadewm

GO      ?= go
GOFLAGS ?=
GIT_COMMIT := $(shell git rev-parse HEAD 2>/dev/null || printf unknown)
LDFLAGS := -X main.gitCommit=$(GIT_COMMIT)

.PHONY: all build debug clean install uninstall

all: build

build:
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY) ./cmd/sadewm

debug:
	$(GO) build $(GOFLAGS) -gcflags="all=-N -l" -ldflags "$(LDFLAGS)" -o $(BINARY) ./cmd/sadewm

clean:
	rm -f $(BINARY)
	$(GO) clean -cache

install: build
	install -Dm755 $(BINARY) $(DESTDIR)$(BINDIR)/$(BINARY)

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/$(BINARY)
