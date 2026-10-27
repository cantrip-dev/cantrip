#!/bin/sh
# Adds a `cantrip` command that runs this folder's copy of Cantrip. Nothing is downloaded or installed:
# Cantrip uses only Python's standard library. Run it again after moving the folder; delete
# ~/.local/bin/cantrip to remove it.
set -e

here=$(cd "$(dirname "$0")" && pwd)
bin_dir="${CANTRIP_BIN_DIR:-$HOME/.local/bin}"

python=""
for p in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    python=$(command -v "$p"); break
  fi
done
if [ -z "$python" ]; then
  echo "Cantrip needs Python 3.11 or newer. On a Mac: brew install python@3.12, then run ./install.sh again." >&2
  exit 1
fi

mkdir -p "$bin_dir"
cat > "$bin_dir/cantrip" <<SHIM
#!/bin/sh
PYTHONPATH="$here\${PYTHONPATH:+:\$PYTHONPATH}" exec "$python" -m cantrip "\$@"
SHIM
chmod +x "$bin_dir/cantrip"

echo "Added $bin_dir/cantrip (runs $here with $python)."
case ":$PATH:" in
  *":$bin_dir:"*) echo "Type cantrip to open the app." ;;
  *) echo "Add $bin_dir to your PATH, e.g. echo 'export PATH=\"$bin_dir:\$PATH\"' >> ~/.zshrc, then open a new terminal and type cantrip." ;;
esac
