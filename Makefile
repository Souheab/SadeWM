# sadewm - dynamic window manager
# See LICENSE file for copyright and license details.

include config.mk

VPATH = src

SRC = sadewm.c util.c tomlc17.c
OBJ = ${SRC:.c=.o}

all: sadewm

${OBJ}: config.mk

sadewm: ${OBJ}
	${CC} -c ${CFLAGS} $<
	${CC} -o $@ ${OBJ} ${LDFLAGS}

debug: CFLAGS += -DDEBUG -g
debug: sadewm

clean:
	rm -f sadewm ${OBJ} sadewm-${VERSION}.tar.gz

dist: clean
	mkdir -p sadewm-${VERSION}
	cp -R LICENSE Makefile config.mk src sadewm.desktop sadewmctl sadewm-${VERSION}
	tar -cf sadewm-${VERSION}.tar sadewm-${VERSION}
	gzip sadewm-${VERSION}.tar
	rm -rf sadewm-${VERSION}

install: all
	mkdir -p ${DESTDIR}${PREFIX}/bin
	cp -f sadewm ${DESTDIR}${PREFIX}/bin
	chmod 755 ${DESTDIR}${PREFIX}/bin/sadewm
	cp -f sadewmctl ${DESTDIR}${PREFIX}/bin
	chmod 755 ${DESTDIR}${PREFIX}/bin/sadewmctl
	mkdir -p ${DESTDIR}${PREFIX}/share/xsessions
	cp -f sadewm.desktop ${DESTDIR}${PREFIX}/share/xsessions
	chmod 644 ${DESTDIR}${PREFIX}/share/xsessions/sadewm.desktop

uninstall:
	rm -f ${DESTDIR}${PREFIX}/bin/sadewm\
		${DESTDIR}${PREFIX}/bin/sadewmctl

.PHONY: all clean dist install uninstall
