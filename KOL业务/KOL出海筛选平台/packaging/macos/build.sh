#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_ROOT="$(mktemp -d /private/tmp/kol-macos-build.XXXXXX)"
VENV="$BUILD_ROOT/venv"
DIST="$ROOT/dist/macos"
APP_NAME="KOL合作管理平台"
# Release artifact: KOL合作管理平台.dmg
APP="$DIST/$APP_NAME.app"
DMG="$DIST/$APP_NAME.dmg"
SMOKE=0
[[ "${1:-}" == "--smoke" ]] && SMOKE=1
PYTHON="${PYTHON:-python3}"

[[ "$(uname -s)" == "Darwin" ]] || { echo "macOS build must run on macOS" >&2; exit 2; }
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required")'
rm -rf "$DIST"
mkdir -p "$DIST"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt" PyInstaller
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --workpath "$BUILD_ROOT/work" --distpath "$DIST" "$ROOT/packaging/kol-platform.spec"

if [[ -n "${APPLE_SIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ROOT/packaging/macos/entitlements.plist" \
    --sign "$APPLE_SIGN_IDENTITY" "$APP"
  if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
    ditto -c -k --keepParent "$APP" "$BUILD_ROOT/$APP_NAME.zip"
    xcrun notarytool submit "$BUILD_ROOT/$APP_NAME.zip" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
    xcrun stapler staple "$APP"
  fi
else
  echo "APPLE_SIGN_IDENTITY not set; producing unsigned internal build."
fi

if [[ "$SMOKE" -eq 1 ]]; then
  "$APP/Contents/MacOS/$APP_NAME" &
  LAUNCHED_PID=$!
  sleep 3
  kill -0 "$LAUNCHED_PID"
  kill "$LAUNCHED_PID" || true
  echo "Smoke launch passed: $APP"
  exit 0
fi

hdiutil create -volname "$APP_NAME" -srcfolder "$APP" -ov -format UDZO "$DMG"
echo "Created $DMG"
