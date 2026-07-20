package wm

import "testing"

func TestFullscreenRestoreGeometrySurvivesOtherResizes(t *testing.T) {
	c := Client{X: 10, Y: 20, W: 640, H: 480}
	c.rememberFullscreenGeometry()

	// resizeClient updates Old* while a display change resizes fullscreen
	// clients. Those generic fields must not replace the pre-fullscreen state.
	c.OldX, c.OldY, c.OldW, c.OldH = 0, 0, 1920, 1080
	x, y, width, height := c.fullscreenRestoreGeometry()
	if x != 10 || y != 20 || width != 640 || height != 480 {
		t.Fatalf("restore geometry = %d,%d %dx%d, want 10,20 640x480",
			x, y, width, height)
	}
}

func TestFocusWindowTagMask(t *testing.T) {
	tests := []struct {
		name        string
		clientTags  uint32
		currentTags uint32
		want        uint32
	}{
		{name: "already visible", clientTags: 0b101, currentTags: 0b100, want: 0},
		{name: "hidden uses lowest client tag", clientTags: 0b110, currentTags: 0b001, want: 0b010},
		{name: "untagged", clientTags: 0, currentTags: 0b001, want: 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := focusWindowTagMask(tt.clientTags, tt.currentTags); got != tt.want {
				t.Fatalf("focusWindowTagMask(%b, %b) = %b, want %b",
					tt.clientTags, tt.currentTags, got, tt.want)
			}
		})
	}
}
