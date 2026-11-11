#!/usr/bin/env bash
# Estado del bot (trader/) cifrado con STATE_KEY en la rama "state". El repositorio es publico:
# en la rama solo viaja trader.tar.gz.enc, nunca texto plano.
#   bash scripts/sync_state.sh restore   # descifra la ultima copia en $STATE_DIR/trader
#   bash scripts/sync_state.sh save      # cifra $STATE_DIR/trader y sube la copia a la rama state
set -euo pipefail

BRANCH="state"
FILE="trader.tar.gz.enc"
STATE_DIR="${STATE_DIR:-${RUNNER_TEMP:-$(mktemp -d)}/bot-state}"
PACK_DIR="$(dirname "$STATE_DIR")/bot-state-pack"
CIPHER=(openssl enc -aes-256-cbc -pbkdf2 -md sha256 -pass env:STATE_KEY)

require_key() {
  [ -n "${STATE_KEY:-}" ] || { echo "Falta el secreto STATE_KEY" >&2; exit 1; }
}

# Imprime el commit de la rama state; vacio si la rama no existe. Falla si el remoto no responde.
remote_head() {
  local rc=0
  git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null || rc=$?
  if [ "$rc" -eq 2 ]; then
    return 0
  fi
  if [ "$rc" -ne 0 ]; then
    echo "No pude consultar el remoto (codigo $rc)" >&2
    exit 1
  fi
  git fetch --quiet --depth 1 origin "$BRANCH"
  git rev-parse FETCH_HEAD
}

restore() {
  require_key
  local head tmp
  head="$(remote_head)"
  if [ -z "$head" ]; then
    echo "Rama $BRANCH no existe: empiezo con estado vacio"
    mkdir -p "$STATE_DIR/trader"
    return 0
  fi
  tmp="$(mktemp -d)"
  git show "$head:$FILE" | "${CIPHER[@]}" -d | tar -xzf - -C "$tmp"
  rm -rf "$STATE_DIR/trader"
  mkdir -p "$STATE_DIR"
  mv "$tmp/trader" "$STATE_DIR/trader"
  echo "Estado restaurado desde $head"
}

save() {
  require_key
  if [ ! -d "$STATE_DIR/trader" ]; then
    echo "No hay estado que guardar (la restauracion no se completo)"
    return 0
  fi
  local parent tree commit
  parent="$(remote_head)"
  mkdir -p "$PACK_DIR"
  tar -czf - -C "$STATE_DIR" trader | "${CIPHER[@]}" -salt -out "$PACK_DIR/$FILE"

  export GIT_DIR="$(git rev-parse --absolute-git-dir)"
  export GIT_INDEX_FILE="$(mktemp -u)"
  export GIT_AUTHOR_NAME="trader-bot" GIT_AUTHOR_EMAIL="trader-bot@users.noreply.github.com"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  if [ -n "$parent" ]; then
    git read-tree "$parent"
  fi
  (cd "$PACK_DIR" && GIT_WORK_TREE="$PACK_DIR" git add -A "$FILE")
  tree="$(git write-tree)"
  commit="$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "chore: estado cifrado del bot $(date -u +%Y-%m-%dT%H:%MZ)")"
  git push --quiet origin "$commit:refs/heads/$BRANCH"
  echo "Estado guardado en $BRANCH: $commit"
}

case "${1:-}" in
  restore) restore ;;
  save) save ;;
  *) echo "Uso: sync_state.sh restore|save" >&2; exit 2 ;;
esac
