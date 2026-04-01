import Quickshell
import Quickshell.Io
import Quickshell.Services.Mpris as MprisServices
import "./" as LocalServices
import QtQuick

// DebugService provides an IPC interface for the bot (or user) to 
// inspect the live shell state using QML evaluations.
Item {
    IpcHandler {
        target: "debug"

        function evaluate(code: string): string {
            try {
                // Warning: eval() is powerful. Only use locally.
                let result = eval(code);
                
                if (typeof result === 'object' && result !== null) {
                    return JSON.stringify(result);
                } else {
                    return String(result);
                }
            } catch (e) {
                return "Error: " + e.message;
            }
        }
    }
}
