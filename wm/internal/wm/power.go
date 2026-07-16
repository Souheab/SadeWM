package wm

/*
#cgo pkg-config: x11 xext xscrnsaver
#include <X11/Xlib.h>
#include <X11/extensions/dpms.h>
#include <X11/extensions/scrnsaver.h>

static int sade_apply_monitor_timeout(Display *dpy, unsigned int timeout_seconds) {
    int event_base = 0;
    int error_base = 0;

    if (dpy == NULL) {
        return 0;
    }

    if (timeout_seconds == 0) {
        XSetScreenSaver(dpy, 0, 0, DontPreferBlanking, DefaultExposures);
        if (DPMSQueryExtension(dpy, &event_base, &error_base) && DPMSCapable(dpy)) {
            DPMSDisable(dpy);
        }
        XFlush(dpy);
        return 1;
    }

    if (!DPMSQueryExtension(dpy, &event_base, &error_base) || !DPMSCapable(dpy)) {
        return 0;
    }

    XSetScreenSaver(dpy, 0, 0, DontPreferBlanking, DefaultExposures);
    if (!DPMSSetTimeouts(dpy, 0, 0, (CARD16)timeout_seconds)) {
        return 0;
    }
    if (!DPMSEnable(dpy)) {
        return 0;
    }
    XFlush(dpy);
    return 1;
}

static int sade_query_idle_ms(Display *dpy, unsigned long *idle_ms) {
    int event_base = 0;
    int error_base = 0;

    if (dpy == NULL || idle_ms == NULL ||
        !XScreenSaverQueryExtension(dpy, &event_base, &error_base)) {
        return 0;
    }

    XScreenSaverInfo *info = XScreenSaverAllocInfo();
    if (info == NULL) {
        return 0;
    }

    Status status = XScreenSaverQueryInfo(dpy, DefaultRootWindow(dpy), info);
    if (status) {
        *idle_ms = info->idle;
    }
    XFree(info);
    return status != 0;
}
*/
import "C"

import (
	"os/exec"
	"time"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

const powerPollInterval = 5 * time.Second

// ApplyPowerSettings applies monitor DPMS behavior and updates the idle-sleep
// timer used by the main event loop.
func (wm *WM) ApplyPowerSettings() {
	wm.sleepTimeoutMinutes = 0
	wm.sleepTriggered = false

	if wm.NoConfig || wm.SettingsPath == "" {
		return
	}
	settings := config.LoadSettingsTOML(wm.SettingsPath)
	if settings == nil || settings.Power == nil {
		return
	}

	if settings.Power.SleepTimeoutMinutes > 0 {
		wm.sleepTimeoutMinutes = settings.Power.SleepTimeoutMinutes
	}
	if wm.XlibDpy == nil {
		return
	}

	timeoutSeconds := monitorTimeoutSeconds(settings.Power.MonitorTimeoutMinutes)
	if C.sade_apply_monitor_timeout(
		(*C.Display)(wm.XlibDpy),
		C.uint(timeoutSeconds),
	) == 0 {
		util.LogDebug("power settings: X11 DPMS is unavailable")
	}
}

func monitorTimeoutSeconds(minutes int) uint {
	if minutes <= 0 {
		return 0
	}
	const maxDPMSSeconds = 65535
	if minutes > maxDPMSSeconds/60 {
		return maxDPMSSeconds
	}
	return uint(minutes * 60)
}

func evaluateIdleSleep(
	idleMilliseconds uint64,
	timeoutMinutes int,
	alreadyTriggered bool,
) (shouldSuspend bool, triggered bool) {
	if timeoutMinutes <= 0 {
		return false, false
	}

	const millisecondsPerMinute = uint64(60 * 1000)
	minutes := uint64(timeoutMinutes)
	if minutes > ^uint64(0)/millisecondsPerMinute {
		return false, false
	}
	timeout := minutes * millisecondsPerMinute
	if idleMilliseconds < timeout {
		return false, false
	}
	return !alreadyTriggered, true
}

func (wm *WM) checkIdleSleep() {
	if wm.sleepTimeoutMinutes <= 0 || wm.XlibDpy == nil {
		wm.sleepTriggered = false
		return
	}

	var idleMilliseconds C.ulong
	if C.sade_query_idle_ms((*C.Display)(wm.XlibDpy), &idleMilliseconds) == 0 {
		return
	}

	shouldSuspend, triggered := evaluateIdleSleep(
		uint64(idleMilliseconds),
		wm.sleepTimeoutMinutes,
		wm.sleepTriggered,
	)
	wm.sleepTriggered = triggered
	if !shouldSuspend {
		return
	}

	go func() {
		if err := exec.Command("systemctl", "suspend").Run(); err != nil {
			util.LogDebug("power settings: suspend failed: %v", err)
		}
	}()
}
