#!/usr/bin/env bash
# learned-behavior installer
#
# Creates the data directory, copies learning.py into place, and symlinks a
# `learned-behavior` CLI into $HOME/.local/bin.
#
# Override locations:
#   LEARNED_BEHAVIOR_HOME  — data dir (default: $XDG_DATA_HOME/learned-behavior or ~/.local/share/learned-behavior)
#   INSTALL_BIN            — where to place the CLI symlink (default: ~/.local/bin)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${LEARNED_BEHAVIOR_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/learned-behavior}"
BIN_DIR="${INSTALL_BIN:-$HOME/.local/bin}"

mkdir -p "$DATA_HOME/scripts" "$DATA_HOME/config" "$BIN_DIR"

# Point scripts/learning.py at the repo copy so updates via `git pull` propagate.
ln -sf "$REPO_DIR/learning.py" "$DATA_HOME/scripts/learning.py"
ln -sf "$REPO_DIR/config/default-skill-registry.json" "$DATA_HOME/config/default-skill-registry.json"

# CLI shim
CLI="$BIN_DIR/learned-behavior"
cat >"$CLI" <<EOF
#!/usr/bin/env bash
exec python3 "$REPO_DIR/learning.py" "\$@"
EOF
chmod +x "$CLI"

echo "Installed:"
echo "  CLI:      $CLI"
echo "  Data dir: $DATA_HOME"
echo "  DB path:  $DATA_HOME/learning.db (created on first run)"
echo
echo "If \$HOME/.local/bin is not on your PATH, add it to your shell profile."
