PREFIX ?= /usr/local
BINDIR  = $(PREFIX)/bin
BINARY  = sadewm

GO      ?= go
GOFLAGS ?=

.PHONY: all build debug clean install uninstall

all: build

build:
	$(GO) build $(GOFLAGS) -o $(BINARY) ./cmd/sadewm

debug:
	$(GO) build $(GOFLAGS) -gcflags="all=-N -l" -o $(BINARY) ./cmd/sadewm

clean:
	rm -f $(BINARY)
	$(GO) clean -cache

install: build
	install -Dm755 $(BINARY) $(DESTDIR)$(BINDIR)/$(BINARY)

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/$(BINARY)
