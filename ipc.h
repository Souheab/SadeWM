/* ipc.h - Unix domain socket IPC interface for sadewm.
 * ipc.c is #included at the bottom of dwm.c so it can access static symbols.
 * Only this header is needed by callers within dwm.c.
 */

#include <errno.h>
#include <sys/select.h>

void ipc_setup(void);
void ipc_teardown(void);
void ipc_poll(void);
int  ipc_fd(void);
