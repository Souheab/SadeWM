package main

import "testing"

func TestCommitHashUsesInjectedValue(t *testing.T) {
	original := gitCommit
	gitCommit = "0123456789abcdef"
	t.Cleanup(func() {
		gitCommit = original
	})

	if got := commitHash(); got != gitCommit {
		t.Fatalf("commitHash() = %q, want %q", got, gitCommit)
	}
}
