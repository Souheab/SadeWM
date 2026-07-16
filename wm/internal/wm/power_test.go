package wm

import "testing"

func TestMonitorTimeoutSeconds(t *testing.T) {
	tests := []struct {
		name    string
		minutes int
		want    uint
	}{
		{name: "disabled", minutes: 0, want: 0},
		{name: "negative", minutes: -1, want: 0},
		{name: "ten minutes", minutes: 10, want: 600},
		{name: "clamped to DPMS maximum", minutes: 2000, want: 65535},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := monitorTimeoutSeconds(tt.minutes); got != tt.want {
				t.Fatalf("monitorTimeoutSeconds(%d) = %d, want %d", tt.minutes, got, tt.want)
			}
		})
	}
}

func TestEvaluateIdleSleep(t *testing.T) {
	tests := []struct {
		name             string
		idleMilliseconds uint64
		timeoutMinutes   int
		alreadyTriggered bool
		wantSuspend      bool
		wantTriggered    bool
	}{
		{name: "disabled", idleMilliseconds: 600_000, timeoutMinutes: 0},
		{name: "active", idleMilliseconds: 299_999, timeoutMinutes: 5},
		{
			name:             "timeout reached",
			idleMilliseconds: 300_000,
			timeoutMinutes:   5,
			wantSuspend:      true,
			wantTriggered:    true,
		},
		{
			name:             "only once per idle period",
			idleMilliseconds: 600_000,
			timeoutMinutes:   5,
			alreadyTriggered: true,
			wantTriggered:    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotSuspend, gotTriggered := evaluateIdleSleep(
				tt.idleMilliseconds,
				tt.timeoutMinutes,
				tt.alreadyTriggered,
			)
			if gotSuspend != tt.wantSuspend || gotTriggered != tt.wantTriggered {
				t.Fatalf(
					"evaluateIdleSleep() = (%t, %t), want (%t, %t)",
					gotSuspend,
					gotTriggered,
					tt.wantSuspend,
					tt.wantTriggered,
				)
			}
		})
	}
}
