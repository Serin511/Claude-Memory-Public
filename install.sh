#!/usr/bin/env bash
set -euo pipefail

SYNC_DIR="$HOME/.claude-sync"
CLAUDE_DIR="$HOME/.claude"

# Accept repo URL as first argument or CLAUDE_SYNC_REPO env var
REPO_URL="${1:-${CLAUDE_SYNC_REPO:-}}"

if [ -z "$REPO_URL" ] && [ ! -d "$SYNC_DIR/.git" ]; then
  echo "Usage: install.sh <your-fork-repo-url>"
  echo ""
  echo "  Example: ./install.sh https://github.com/yourname/Claude-Memory.git"
  echo ""
  echo "  Or set CLAUDE_SYNC_REPO env var:"
  echo "    CLAUDE_SYNC_REPO=https://github.com/yourname/Claude-Memory.git ./install.sh"
  exit 1
fi

# --- helpers ---

link_item() {
  local src="$1"
  local dst="$2"

  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    echo "  backup: $dst → ${dst}.bak"
    mv "$dst" "${dst}.bak"
  fi

  ln -sf "$src" "$dst"
  echo "  linked: $dst → $src"
}

# --- clone if needed ---

if [ ! -d "$SYNC_DIR/.git" ]; then
  echo "Cloning repo..."
  git clone "$REPO_URL" "$SYNC_DIR"
else
  echo "Already installed at $SYNC_DIR (skipping clone)"
fi

# --- ensure ~/.claude exists ---

mkdir -p "$CLAUDE_DIR"

# --- symlink top-level config ---

echo "Setting up symlinks..."

for target in CLAUDE.md settings.json commands rules; do
  src="$SYNC_DIR/$target"
  dst="$CLAUDE_DIR/$target"

  if [ -e "$src" ]; then
    link_item "$src" "$dst"
  fi
done

# --- symlink project memory directories (opt-in) ---

if [ "${CLAUDE_SYNC_PROJECTS:-0}" = "1" ] && [ -d "$SYNC_DIR/projects" ]; then
  echo "Setting up project memory symlinks..."
  for project_dir in "$SYNC_DIR/projects"/*/; do
    [ -d "$project_dir" ] || continue
    project_name=$(basename "$project_dir")
    memory_src="$SYNC_DIR/projects/$project_name/memory"

    if [ -d "$memory_src" ]; then
      mkdir -p "$CLAUDE_DIR/projects/$project_name"
      link_item "$memory_src" "$CLAUDE_DIR/projects/$project_name/memory"
    fi
  done
fi

# --- detect shell and rc file ---

detect_shell_rc() {
  local user_shell
  user_shell=$(basename "${SHELL:-/bin/bash}")

  case "$user_shell" in
    zsh)  echo "$HOME/.zshrc" ;;
    bash) echo "$HOME/.bashrc" ;;
    *)    echo "$HOME/.bashrc" ;;
  esac
}

RC_FILE=$(detect_shell_rc)
SHELL_NAME=$(basename "${SHELL:-/bin/bash}")
MARKER="# >>> claude-sync >>>"

echo "Detected shell: $SHELL_NAME → $RC_FILE"

# --- add auto-sync hooks ---

END_MARKER="# <<< claude-sync <<<"

# Remove old hook block if present (allows upgrade on re-install)
if grep -q "$MARKER" "$RC_FILE" 2>/dev/null; then
  echo "Removing old auto-sync hooks from $RC_FILE..."
  sed -i.sed-bak "/$MARKER/,/$END_MARKER/d" "$RC_FILE"
  rm -f "${RC_FILE}.sed-bak"
fi

# Ensure rc file exists (some minimal systems may not have it)
touch "$RC_FILE"

echo "Adding auto-sync hooks to $RC_FILE..."
cat >> "$RC_FILE" << 'RCEOF'

# >>> claude-sync >>>
# Auto-sync Claude Code config across machines via Git

_claude_sync_push() {
  [ -x "$HOME/.claude-sync/sync.sh" ] && "$HOME/.claude-sync/sync.sh" push 2>/dev/null || true
}

_claude_sync_pull_if_needed() {
  local stamp="$HOME/.claude-sync/.last-pull"
  local now
  now=$(date +%s)

  if [ -f "$stamp" ]; then
    local last
    last=$(cat "$stamp")
    # cooldown: 5 minutes
    if (( now - last < 300 )); then
      return 0
    fi
  fi

  if [ -x "$HOME/.claude-sync/sync.sh" ]; then
    "$HOME/.claude-sync/sync.sh" pull 2>/dev/null
    echo "$now" > "$stamp"
  fi
}

# Manual sync commands
claude-sync() {
  if [ -x "$HOME/.claude-sync/sync.sh" ]; then
    "$HOME/.claude-sync/sync.sh" "$@"
  else
    echo "claude-sync: sync.sh not found at ~/.claude-sync/sync.sh" >&2
    return 1
  fi
}

# Push local config before SSH, pull on remote after login
ssh() {
  _claude_sync_push
  command ssh "$@"
}

# Auto-pull on login shell (remote machines receive this on SSH login)
_claude_sync_is_login() {
  if [ -n "${ZSH_VERSION:-}" ]; then
    [[ -o login ]]
  elif [ -n "${BASH_VERSION:-}" ]; then
    shopt -q login_shell 2>/dev/null
  else
    case "$0" in -*) return 0 ;; *) return 1 ;; esac
  fi
}

if _claude_sync_is_login; then
  _claude_sync_pull_if_needed
fi
# <<< claude-sync <<<
RCEOF
echo "  Added to $RC_FILE"

# For bash: ensure .bash_profile sources .bashrc (SSH starts a login shell)
if [ "$SHELL_NAME" = "bash" ]; then
  BASH_PROFILE="$HOME/.bash_profile"
  if [ ! -f "$BASH_PROFILE" ] || ! grep -q "\.bashrc" "$BASH_PROFILE" 2>/dev/null; then
    echo '' >> "$BASH_PROFILE"
    echo '# Source .bashrc for login shells' >> "$BASH_PROFILE"
    echo '[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"' >> "$BASH_PROFILE"
    echo "  Ensured $BASH_PROFILE sources .bashrc"
  fi
fi

echo ""
echo "Done! Claude config sync is ready."
echo "  Repo: $SYNC_DIR"
echo "  Run 'source $RC_FILE' to activate auto-sync."
