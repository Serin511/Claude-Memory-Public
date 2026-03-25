#!/usr/bin/env bash
set -euo pipefail

SYNC_DIR="$HOME/.claude-sync"
CLAUDE_DIR="$HOME/.claude"

SYNC_TARGETS=(CLAUDE.md settings.json commands rules)

cd "$SYNC_DIR"

# --- helpers ---

repair_symlinks() {
  for target in "${SYNC_TARGETS[@]}"; do
    local claude_path="$CLAUDE_DIR/$target"
    local sync_path="$SYNC_DIR/$target"

    # If Claude replaced a symlink with a regular file, copy back and re-link
    if [ -e "$claude_path" ] && [ ! -L "$claude_path" ]; then
      rm -rf "$sync_path"
      cp -a "$claude_path" "$sync_path"
      rm -rf "$claude_path"
      ln -sf "$sync_path" "$claude_path"
    fi
  done
}

collect_project_memory() {
  [ "${CLAUDE_SYNC_PROJECTS:-0}" = "1" ] || return 0
  [ -d "$CLAUDE_DIR/projects" ] || return 0

  for project_dir in "$CLAUDE_DIR/projects"/*/; do
    [ -d "$project_dir" ] || continue
    local project_name
    project_name=$(basename "$project_dir")
    local memory_src="$project_dir/memory"
    local memory_dst="$SYNC_DIR/projects/$project_name/memory"

    # Skip if already a symlink (pointing to repo)
    [ -L "$memory_src" ] && continue

    if [ -d "$memory_src" ] && [ "$(ls -A "$memory_src" 2>/dev/null)" ]; then
      mkdir -p "$memory_dst"
      cp -a "$memory_src"/* "$memory_dst/" 2>/dev/null || true
      rm -rf "$memory_src"
      ln -sf "$memory_dst" "$memory_src"
    fi
  done
}

ensure_symlinks() {
  # Top-level config
  for target in "${SYNC_TARGETS[@]}"; do
    local claude_path="$CLAUDE_DIR/$target"
    local sync_path="$SYNC_DIR/$target"

    if [ -e "$sync_path" ] && [ ! -L "$claude_path" ]; then
      if [ -e "$claude_path" ]; then
        mv "$claude_path" "${claude_path}.bak"
      fi
      ln -sf "$sync_path" "$claude_path"
    fi
  done

  # Project memory (opt-in)
  if [ "${CLAUDE_SYNC_PROJECTS:-0}" = "1" ] && [ -d "$SYNC_DIR/projects" ]; then
    for project_dir in "$SYNC_DIR/projects"/*/; do
      [ -d "$project_dir" ] || continue
      local project_name
      project_name=$(basename "$project_dir")
      local memory_src="$SYNC_DIR/projects/$project_name/memory"
      local memory_dst="$CLAUDE_DIR/projects/$project_name/memory"

      if [ -d "$memory_src" ]; then
        mkdir -p "$CLAUDE_DIR/projects/$project_name"
        if [ ! -L "$memory_dst" ]; then
          [ -e "$memory_dst" ] && mv "$memory_dst" "${memory_dst}.bak"
          ln -sf "$memory_src" "$memory_dst"
        fi
      fi
    done
  fi
}

# --- commands ---

push() {
  repair_symlinks
  collect_project_memory

  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "sync: $(hostname -s) $(date '+%Y-%m-%d %H:%M')"
    git push origin main 2>/dev/null || git push origin master 2>/dev/null || true
  fi
}

pull() {
  git fetch origin 2>/dev/null

  local branch
  branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")

  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$branch" 2>/dev/null)" ]; then
    git pull --rebase --autostash origin "$branch" 2>/dev/null || true
  fi

  ensure_symlinks
}

case "${1:-help}" in
  push) push ;;
  pull) pull ;;
  *)
    echo "Usage: $(basename "$0") {push|pull}"
    echo "  push  Sync local changes to remote"
    echo "  pull  Pull remote changes and set up symlinks"
    ;;
esac
