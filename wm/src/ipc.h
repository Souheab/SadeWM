/* ipc.h - Unix domain socket IPC interface for sadewm.
 * ipc.c is #included at the bottom of sadewm.c so it can access static symbols.
 * Only this header is needed by callers within sadewm.c.
 */

#include <errno.h>
#include <sys/select.h>

void ipc_setup(void);
void ipc_teardown(void);
void ipc_poll(void);
int  ipc_fd(void);
