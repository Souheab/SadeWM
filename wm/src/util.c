/* See LICENSE file for copyright and license details. */
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "util.h"

static int logfd = -1;

void
log_init(const char *path)
{
	char dir[512];
	char *slash;

	snprintf(dir, sizeof dir, "%s", path);
	slash = strrchr(dir, '/');
	if (slash) {
		*slash = '\0';
		mkdir(dir, 0755);
	}
	logfd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
	if (logfd >= 0) {
		time_t t = time(NULL);
		struct tm *tm = localtime(&t);
		char timebuf[64];
		char buf[128];
		int len;

		strftime(timebuf, sizeof timebuf, "%Y-%m-%d %H:%M:%S", tm);
		len = snprintf(buf, sizeof buf, "\n--- sadewm started at %s ---\n", timebuf);
		if (write(logfd, buf, len) == -1) {}
	}
}

int
get_logfd(void)
{
	return logfd;
}

void
die(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (fmt[0] && fmt[strlen(fmt)-1] == ':') {
		fputc(' ', stderr);
		perror(NULL);
	} else {
		fputc('\n', stderr);
	}

	if (logfd >= 0) {
		time_t t = time(NULL);
		struct tm *tm = localtime(&t);
		char timebuf[64];
		char msgbuf[512];
		char buf[640];
		int len;

		strftime(timebuf, sizeof timebuf, "%Y-%m-%d %H:%M:%S", tm);

		va_start(ap, fmt);
		vsnprintf(msgbuf, sizeof msgbuf, fmt, ap);
		va_end(ap);

		if (fmt[0] && fmt[strlen(fmt)-1] == ':') {
			len = snprintf(buf, sizeof buf, "[%s] fatal: %s %s\n",
				timebuf, msgbuf, strerror(errno));
		} else {
			len = snprintf(buf, sizeof buf, "[%s] fatal: %s\n",
				timebuf, msgbuf);
		}
		if (write(logfd, buf, len) == -1) {}
	}

	exit(1);
}

void *
ecalloc(size_t nmemb, size_t size)
{
	void *p;

	if (!(p = calloc(nmemb, size)))
		die("calloc:");
	return p;
}
