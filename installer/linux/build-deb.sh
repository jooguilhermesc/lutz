#!/usr/bin/env bash
# Build a .deb package wrapping the lutz PyInstaller binary.
# Run from the repository root after PyInstaller has produced dist/lutz.
#
# Usage:
#   bash installer/linux/build-deb.sh 0.3.0
#
set -euo pipefail

VERSION="${1:-0.3.0}"
PKG="lutz-research_${VERSION}_amd64"
ROOT="dist/deb/${PKG}"

echo "▶ Building .deb: ${PKG}.deb"

# ── Directory structure ───────────────────────────────────────────────────────
mkdir -p "${ROOT}/usr/bin"
mkdir -p "${ROOT}/usr/share/applications"
mkdir -p "${ROOT}/usr/share/pixmaps"
mkdir -p "${ROOT}/usr/share/doc/lutz-research"
mkdir -p "${ROOT}/DEBIAN"

# ── Binary ───────────────────────────────────────────────────────────────────
cp dist/lutz "${ROOT}/usr/bin/lutz"
chmod 755 "${ROOT}/usr/bin/lutz"

# ── Desktop entry ─────────────────────────────────────────────────────────────
cp installer/linux/lutz.desktop "${ROOT}/usr/share/applications/lutz.desktop"

# ── Icon (use placeholder if not available) ───────────────────────────────────
if [ -f "web/public/lutz.png" ]; then
  cp web/public/lutz.png "${ROOT}/usr/share/pixmaps/lutz.png"
fi

# ── Docs / license ───────────────────────────────────────────────────────────
cp LICENSE "${ROOT}/usr/share/doc/lutz-research/copyright"
gzip -9 -c - > "${ROOT}/usr/share/doc/lutz-research/changelog.gz" <<'EOF'
lutz-research (0.3.0) stable; urgency=low
  * Initial Debian package release.
 -- João Guilherme <silvacabraljoaoguilherme@gmail.com>  Thu, 22 May 2026 00:00:00 +0000
EOF

# ── DEBIAN/control ───────────────────────────────────────────────────────────
INSTALLED_SIZE=$(du -sk "${ROOT}/usr" | cut -f1)

cat > "${ROOT}/DEBIAN/control" <<EOF
Package: lutz-research
Version: ${VERSION}
Section: science
Priority: optional
Architecture: amd64
Installed-Size: ${INSTALLED_SIZE}
Maintainer: João Guilherme <silvacabraljoaoguilherme@gmail.com>
Homepage: https://github.com/jooguilhermesc/lutz
Description: AI-powered academic article screening tool
 Lutz Research is a tool for systematic review and screening of
 academic articles using large language models and semantic search.
 .
 Run 'lutz web' to open the browser interface.
EOF

# ── DEBIAN/postinst ───────────────────────────────────────────────────────────
cat > "${ROOT}/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
# Update desktop database so the launcher appears in app menus
if command -v update-desktop-database > /dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
POSTINST
chmod 755 "${ROOT}/DEBIAN/postinst"

# ── DEBIAN/postrm ─────────────────────────────────────────────────────────────
cat > "${ROOT}/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if command -v update-desktop-database > /dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
POSTRM
chmod 755 "${ROOT}/DEBIAN/postrm"

# ── Build ─────────────────────────────────────────────────────────────────────
dpkg-deb --build --root-owner-group "${ROOT}" "dist/${PKG}.deb"
echo "✓ dist/${PKG}.deb"
