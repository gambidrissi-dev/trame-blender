# Linux Makefile for installing GUI desktop files, icons and ifc file associations

DESTDIR = ${HOME}/.local

install :
	mkdir -p \
	${DESTDIR}/bin \
	${DESTDIR}/share/icons/hicolor/128x128/apps \
	${DESTDIR}/share/icons/hicolor/128x128/mimetypes \
	${DESTDIR}/share/applications \
	${DESTDIR}/share/mime/packages
	cp trame ${DESTDIR}/bin/
	chmod +x ${DESTDIR}/bin/trame
	cp trame.png ${DESTDIR}/share/icons/hicolor/128x128/apps/
	cp trame.desktop ${DESTDIR}/share/applications/
	cp trame.xml ${DESTDIR}/share/mime/packages/
	cp x-ifc_128x128.png ${DESTDIR}/share/icons/hicolor/128x128/mimetypes/x-ifc.png
	update-mime-database ${DESTDIR}/share/mime/ || true
	update-desktop-database ${DESTDIR}/share/applications/ || true

uninstall :
	rm -f \
	${DESTDIR}/bin/trame \
	${DESTDIR}/share/icons/hicolor/128x128/apps/trame.png \
	${DESTDIR}/share/applications/trame.desktop \
	${DESTDIR}/share/mime/packages/trame.xml \
	${DESTDIR}/share/icons/hicolor/128x128/mimetypes/x-ifc.png
	update-mime-database ${DESTDIR}/share/mime/ || true
	update-desktop-database ${DESTDIR}/share/applications/ || true
