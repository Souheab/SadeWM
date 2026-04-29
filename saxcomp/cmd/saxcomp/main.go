package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/sadewm/sadewm/saxcomp/internal/compositor"
)

func main() {
	display := flag.String("display", "", "X display to connect to (default: $DISPLAY)")
	debug := flag.Bool("debug", false, "enable debug logging")
	flag.Parse()

	log.SetPrefix("saxcomp: ")
	log.SetFlags(log.Ltime | log.Lshortfile)

	if *display == "" {
		*display = os.Getenv("DISPLAY")
	}

	comp, err := compositor.New(*display, *debug)
	if err != nil {
		log.Fatalf("init: %v", err)
	}
	defer comp.Close()

	log.Printf("compositing display %s", *display)

	// Handle SIGTERM / SIGINT for graceful shutdown.
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-sigs
		comp.Close()
		os.Exit(0)
	}()

	comp.Run()
}
