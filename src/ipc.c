/* ipc.c - Unix domain socket IPC for sadewm.
 *
 * This file is NOT compiled independently — it is #included at the bottom of
 * sadewm.c so that it shares the same translation unit and can access all static
 * symbols (selmon, view, tag, toggleview, toggletag, …) without any linkage
 * gymnastics.
 *
 * Protocol (one message per connection, then close):
 *   request  — compact JSON sent by the client, e.g. {"cmd":"view","mask":4}
 *   response — compact JSON followed by a newline, written back before close
 *
 * Supported commands:
 *   {"cmd":"get_state"}            — returns full WM state
 *   {"cmd":"view","mask":<uint>}
 *   {"cmd":"toggleview","mask":<uint>}
 *   {"cmd":"tag","mask":<uint>}
 *   {"cmd":"toggletag","mask":<uint>}
 */

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>

static int ipc_server_fd = -1;

int
ipc_fd(void)
{
  return ipc_server_fd;
}

void
ipc_setup(void)
{
  struct sockaddr_un addr;
  int flags;

  ipc_server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
  if (ipc_server_fd < 0)
    die("ipc: socket failed");

  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, IPC_SOCKET_PATH, sizeof(addr.sun_path) - 1);

  unlink(IPC_SOCKET_PATH); /* remove stale socket from a previous run */

  if (bind(ipc_server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    die("ipc: bind failed");
  if (listen(ipc_server_fd, 8) < 0)
    die("ipc: listen failed");

  flags = fcntl(ipc_server_fd, F_GETFL, 0);
  fcntl(ipc_server_fd, F_SETFL, flags | O_NONBLOCK);
}

void
ipc_teardown(void)
{
  if (ipc_server_fd >= 0) {
    close(ipc_server_fd);
    ipc_server_fd = -1;
  }
  unlink(IPC_SOCKET_PATH);
}

/* Best-effort write; errors are ignored (client may have disconnected). */
static void
ipc_write(int fd, const char *buf, size_t len)
{
  ssize_t r = write(fd, buf, len);
  (void)r;
}

/* Append a JSON-escaped copy of src into dst, return chars written. */
static int
ipc_json_escape(const char *src, char *dst, int dstsize)
{
  int i = 0;
  while (*src && i < dstsize - 2) {
    if (*src == '"' || *src == '\\')
      dst[i++] = '\\';
    dst[i++] = *src++;
  }
  dst[i] = '\0';
  return i;
}

static void
ipc_handle_get_state(int fd)
{
  char buf[32768];
  char ename[512];
  int n = 0;
  int first = 1;
  Client *c;

  n += snprintf(buf + n, sizeof(buf) - n,
    "{\"ok\":true"
    ",\"tag_mask\":%u"
    ",\"layout\":\"%s\""
    ",\"mfact\":%.2f"
    ",\"nmaster\":%d"
    ",\"gaps\":%d"
    ",\"isrighttiled\":%s"
    ",\"clients\":[",
    selmon->tagset[selmon->seltags],
    selmon->ltsymbol,
    selmon->mfact,
    selmon->nmaster,
    selmon->gappx,
    selmon->isrighttiled ? "true" : "false");

  for (c = selmon->clients; c; c = c->next) {
    ipc_json_escape(c->name, ename, sizeof(ename));
    n += snprintf(buf + n, sizeof(buf) - n,
      "%s{\"name\":\"%s\",\"tags\":%u"
      ",\"floating\":%s,\"maximized\":%s,\"focused\":%s}",
      first ? "" : ",",
      ename,
      c->tags,
      c->isfloating  ? "true" : "false",
      c->maximized   ? "true" : "false",
      (c == selmon->sel) ? "true" : "false");
    first = 0;
  }

  n += snprintf(buf + n, sizeof(buf) - n, "]}\n");
  ipc_write(fd, buf, n);
}

static void
ipc_handle_tags_state(int fd)
{
  char buf[256];
  int n = 0;
  int i;
  unsigned int occ = 0;
  Client *c;

  for (c = selmon->clients; c; c = c->next)
    occ |= c->tags;

  n += snprintf(buf + n, sizeof(buf) - n, "{\"ok\":true,\"tags_state\":[");
  for (i = 0; i < LENGTH(tags); i++) {
    char state = 'I';
    if (selmon->tagset[selmon->seltags] & (1 << i))
      state = 'A';
    else if (occ & (1 << i))
      state = 'O';
    n += snprintf(buf + n, sizeof(buf) - n, "%s\"%c\"", i == 0 ? "" : ",", state);
  }
  n += snprintf(buf + n, sizeof(buf) - n, "]}\n");
  ipc_write(fd, buf, n);
}

static void
ipc_handle_tag_cmd(int fd, const char *cmd, unsigned int mask)
{
  const char *ok = "{\"ok\":true}\n";
  Arg a = {.ui = mask};

  if      (strcmp(cmd, "view")       == 0) view(&a);
  else if (strcmp(cmd, "toggleview") == 0) toggleview(&a);
  else if (strcmp(cmd, "tag")        == 0) tag(&a);
  else if (strcmp(cmd, "toggletag")  == 0) toggletag(&a);

  ipc_write(fd, ok, strlen(ok));
}

void
ipc_poll(void)
{
  char buf[256];
  char cmd[64] = {0};
  const char *p, *e;
  ssize_t n;
  int cfd, len;

  cfd = accept(ipc_server_fd, NULL, NULL);
  if (cfd < 0)
    return;

  n = read(cfd, buf, sizeof(buf) - 1);
  if (n <= 0) {
    close(cfd);
    return;
  }
  buf[n] = '\0';

  /* extract value of "cmd" field */
  p = strstr(buf, "\"cmd\"");
  if (p) {
    p = strchr(p + 5, '"'); /* skip to opening quote of value */
    if (p) {
      p++;
      e = strchr(p, '"');
      if (e) {
        len = (int)(e - p);
        if (len > 0 && len < (int)sizeof(cmd))
          memcpy(cmd, p, len);
      }
    }
  }

  if (strcmp(cmd, "get_state") == 0) {
    ipc_handle_get_state(cfd);
  } else if (strcmp(cmd, "tags_state") == 0) {
    ipc_handle_tags_state(cfd);
  } else if (strcmp(cmd, "reload") == 0) {
    reloadconfig(NULL);
    const char *ok = "{\"ok\":true}\n";
    ipc_write(cfd, ok, strlen(ok));
  } else if (strcmp(cmd, "view")       == 0
          || strcmp(cmd, "toggleview") == 0
          || strcmp(cmd, "tag")        == 0
          || strcmp(cmd, "toggletag")  == 0) {
    unsigned int mask = 0;
    p = strstr(buf, "\"mask\"");
    if (p) {
      p = strchr(p + 6, ':');
      if (p)
        mask = (unsigned int)atoi(p + 1);
    }
    ipc_handle_tag_cmd(cfd, cmd, mask);
  } else {
    const char *err = "{\"ok\":false,\"error\":\"unknown command\"}\n";
    ipc_write(cfd, err, strlen(err));
  }

  close(cfd);
}
