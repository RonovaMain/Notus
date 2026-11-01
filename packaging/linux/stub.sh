#!/bin/sh
# Notus @VERSION@ — self-extracting portable archive.
# Usage:  ./Notus-@VERSION@-linux-x86_64.run [--target DIR] [--desktop] [--run]
#   --target DIR  extract into DIR (default: ./Notus)
#   --desktop     also add a launcher to ~/.local/share/applications (optional)
#   --run         start Notus right after extraction
# Nothing is installed system-wide; delete the folder to remove the program.
set -e
TARGET="$PWD/Notus"
RUN=0
DESKTOP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --target) [ -n "$2" ] || { echo "--target needs a directory" >&2; exit 2; }; TARGET="$2"; shift 2 ;;
    --desktop) DESKTOP=1; shift ;;
    --run) RUN=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

ARCHIVE_LINE=$(LC_ALL=C awk '/^__NOTUS_ARCHIVE__$/ { print NR + 1; exit }' "$0")
mkdir -p "$TARGET"
echo "Extracting Notus to $TARGET ..."
tail -n +"$ARCHIVE_LINE" "$0" | tar -xzf - -C "$TARGET" --strip-components=1
chmod +x "$TARGET/Notus" "$TARGET"/backend/llama-* 2>/dev/null || true

if [ "$DESKTOP" = 1 ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/notus.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Notus
Comment=Local GGUF chat for old hardware
Exec=$TARGET/Notus
Icon=$TARGET/_internal/assets/icon.png
Terminal=false
Categories=Utility;
DESK
  echo "Launcher added to the applications menu."
fi

echo "Done. Start Notus with: $TARGET/Notus"
if [ "$RUN" = 1 ]; then exec "$TARGET/Notus"; fi
exit 0
__NOTUS_ARCHIVE__
