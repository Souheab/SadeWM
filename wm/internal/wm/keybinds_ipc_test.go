package wm

import (
	"testing"

	"github.com/jezek/xgb/xproto"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/ipc"
)

func TestDefaultKeysIncludeKeybindOverlay(t *testing.T) {
	mod := uint16(config.ModKey)
	for _, key := range config.DefaultKeys() {
		if key.Mod == mod && key.KeyStr == "s" && key.Action == "spawn" {
			argv, ok := key.Arg.V.([]string)
			if !ok || len(argv) != 2 || argv[0] != "sadeshell" || argv[1] != "--open-keybinds" {
				t.Fatalf("unexpected Super+s command: %#v", key.Arg.V)
			}
			return
		}
	}
	t.Fatal("expected Super+s keybind overlay binding")
}

func TestDefaultAltSUsesResidentShellIPC(t *testing.T) {
	alt := uint16(config.AltKey)
	foundAltS := false
	for _, key := range config.DefaultKeys() {
		if key.Mod == alt && key.KeyStr == "Tab" {
			t.Fatal("Alt+Tab must remain unbound")
		}
		if key.Mod == alt && key.KeyStr == "s" {
			foundAltS = true
			if key.Action != "shellcmd" {
				t.Fatalf("Alt+S action = %q, want shellcmd", key.Action)
			}
			if command, ok := key.Arg.V.(string); !ok || command != "open-window-picker" {
				t.Fatalf("unexpected Alt+S shell command: %#v", key.Arg.V)
			}
		}
	}
	if !foundAltS {
		t.Fatal("expected Alt+S window picker binding")
	}
}

func TestFormatKeyMods(t *testing.T) {
	tests := []struct {
		name string
		mask uint16
		want []string
	}{
		{
			name: "super shift",
			mask: uint16(config.ModKey) | uint16(xproto.ModMaskShift),
			want: []string{"Super", "Shift"},
		},
		{
			name: "super ctrl shift",
			mask: uint16(config.ModKey) | uint16(xproto.ModMaskControl) | uint16(xproto.ModMaskShift),
			want: []string{"Super", "Ctrl", "Shift"},
		},
		{
			name: "alt",
			mask: uint16(config.AltKey),
			want: []string{"Alt"},
		},
	}

	for _, tt := range tests {
		got := formatKeyMods(tt.mask)
		if len(got) != len(tt.want) {
			t.Fatalf("%s: got %v, want %v", tt.name, got, tt.want)
		}
		for i := range got {
			if got[i] != tt.want[i] {
				t.Fatalf("%s: got %v, want %v", tt.name, got, tt.want)
			}
		}
	}
}

func TestKeybindsIPCIncludesActiveDefaults(t *testing.T) {
	wm := New()
	resp := wm.handleIPCRequest(&ipc.IPCRequest{Cmd: "keybinds"})
	if resp == nil || !resp.OK {
		t.Fatalf("keybinds response failed: %+v", resp)
	}

	for _, keybind := range resp.Keybinds {
		if keybind.Key == "S" && keybind.Action == "spawn" && keybind.Description == "Show keybinds" {
			return
		}
	}
	t.Fatalf("keybind overlay binding missing from response: %+v", resp.Keybinds)
}

func TestKeybindsIPCReflectsMergedTOMLKeys(t *testing.T) {
	wm := New()
	wm.ActiveKeys = config.MergeKeys(&config.TOMLConfig{
		Keys: []config.TOMLKey{
			{Mod: []string{"super"}, Key: "p", Action: "none"},
			{Mod: []string{"super"}, Key: "x", Action: "spawn", Cmd: "custom-command"},
		},
	}, config.DefaultKeys())

	resp := wm.handleIPCRequest(&ipc.IPCRequest{Cmd: "keybinds"})
	if resp == nil || !resp.OK {
		t.Fatalf("keybinds response failed: %+v", resp)
	}

	foundCustom := false
	for _, keybind := range resp.Keybinds {
		if keybind.Key == "P" && keybind.Action == "spawn" {
			t.Fatalf("removed Super+p binding still present: %+v", keybind)
		}
		if keybind.Key == "X" && keybind.Action == "spawn" && keybind.Description == "Run /bin/sh -c custom-command" {
			foundCustom = true
		}
	}
	if !foundCustom {
		t.Fatalf("custom merged keybind missing from response: %+v", resp.Keybinds)
	}
}
