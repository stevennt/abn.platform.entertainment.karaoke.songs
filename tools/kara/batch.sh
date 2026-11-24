#!/bin/sh
# Publish songs from a queue, one at a time, refusing anything unlicensed.
#
#   tools/kara/batch.sh                  # every row in songs/queue.csv
#   tools/kara/batch.sh --dry-run        # say what would happen, change nothing
#   tools/kara/batch.sh --limit 2        # stop after two songs
#   tools/kara/batch.sh --queue /tmp/q.csv
#
# A row already in index.json is SKIPPED, so the queue is resumable: run it again
# after a failure and it continues where it stopped. A row with no line in
# songs/licenses.csv is REFUSED before any work — this repo is public, so a
# package without a recorded right must never become publishable by accident.
#
# Row format (songs/queue.csv), header required, no commas inside a field:
#   id,title,artist,backing,lyrics,cover,licence,source
#     backing   a file path or an https URL (a URL needs yt-dlp)
#     lyrics    a .lrc or .srt file with the words and their timings
#     cover     an image or a video to take a frame from
#     licence   owned | public-domain | cc-by | user-import
#     source    where it came from, in words ("ABN Asia master, 2019")
#
# The ledger (songs/licenses.csv) is `id,licence,note`, and it is written BEFORE
# a package is built, so the record survives a failed build. batch.sh never
# invents a ledger row.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
APP=${KARA_APP:-$HOME/Workspace/abn.platform.entertainment.karaoke/app}
QUEUE=${QUEUE:-$ROOT/songs/queue.csv}
LEDGER=${LEDGER:-$ROOT/songs/licenses.csv}
INDEX=$ROOT/index.json
WORK=${WORK:-$ROOT/.work}
LIMIT=0
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --limit)
      shift
      LIMIT=${1:?--limit needs a number}
      ;;
    --queue)
      shift
      QUEUE=${1:?--queue needs a file}
      ;;
    *)
      echo "batch: unknown argument '$1'" >&2
      echo "usage: tools/kara/batch.sh [--dry-run] [--limit N] [--queue FILE]" >&2
      exit 2
      ;;
  esac
  shift
done

[ -f "$QUEUE" ] || { echo "batch: no queue at $QUEUE" >&2; exit 2; }
[ -f "$LEDGER" ] || { echo "batch: no ledger at $LEDGER" >&2; exit 2; }
[ -f "$INDEX" ] || { echo "batch: no index at $INDEX" >&2; exit 2; }
[ -d "$APP" ] || { echo "batch: no app at $APP (set KARA_APP)" >&2; exit 2; }

kara() {
  ( cd "$APP" && dart run tool/kara/main.dart "$@" )
}

published() {
  grep -q "\"id\": \"$1\"" "$INDEX" 2>/dev/null
}

licence_of() {
  awk -F, -v id="$1" 'NR > 1 && $1 == id { print $2; exit }' "$LEDGER"
}

allowed_licence() {
  case "$1" in
    owned|public-domain|cc-by|user-import) return 0 ;;
    *) return 1 ;;
  esac
}

PYTHON=${PYTHON:-/Users/thanhson/Workspace/abnvirtualenv/bin/python}

have_ytdlp() {
  command -v yt-dlp >/dev/null 2>&1 ||
    [ -x "$HOME/Workspace/abnvirtualenv/bin/yt-dlp" ]
}

# The loop reads a file, not a pipe: with `tail | while` it would run in a
# subshell, where `exit 1` could not stop the batch.
# The queue is CSV, and a title may contain a comma ("Swing Low, Sweet
# Chariot"), so the fields are split by a real CSV parser and re-joined with a
# unit separator that no title contains. `IFS=, read` alone would turn that row
# into nine fields and shift every column after it.
rows=$(mktemp "${TMPDIR:-/tmp}/kara-queue.XXXXXX")
"$PYTHON" "$ROOT/tools/kara/csv_rows.py" "$QUEUE" > "$rows"
mkdir -p "$WORK"

count=0
separator=$(printf '\037')
while IFS="$separator" read -r id title artist backing lyrics cover licence source; do
  [ -n "${id:-}" ] || continue
  if [ "$LIMIT" -gt 0 ] && [ "$count" -ge "$LIMIT" ]; then
    break
  fi

  if published "$id"; then
    echo "SKIP    $id: already in the index"
    continue
  fi

  recorded=$(licence_of "$id" || true)
  if [ -z "$recorded" ]; then
    echo "REFUSE  $id: no row in songs/licenses.csv — a public catalogue needs the right on record"
    continue
  fi
  if ! allowed_licence "$recorded"; then
    echo "REFUSE  $id: licence '$recorded' is not owned, public-domain, cc-by or user-import"
    continue
  fi
  if [ -n "${licence:-}" ] && [ "$licence" != "$recorded" ]; then
    echo "REFUSE  $id: the queue says '$licence', the ledger says '$recorded'"
    continue
  fi
  if [ -z "${backing:-}" ]; then
    echo "REFUSE  $id: the queue row needs a backing (a file, a URL, or 'auto')"
    continue
  fi
  # `auto` means: build the three inputs from a public-domain recording, with
  # songs/sources/<id>.json naming it. prepare.py refuses a recording whose
  # licence is not free, before any of the expensive work starts.
  if [ "$backing" = auto ]; then
    if [ ! -f "$ROOT/songs/sources/$id.json" ]; then
      echo "REFUSE  $id: backing is 'auto' but songs/sources/$id.json is missing"
      continue
    fi
    echo "PREPARE $id"
    if ! /Users/thanhson/Workspace/abnvirtualenv/bin/python "$ROOT/tools/kara/prepare.py" "$id"; then
      echo "FAILED  $id: prepare"
      continue
    fi
    . "$ROOT/.work/src/$id/vars.sh"
    backing=$BACKING
    lyrics=$LYRICS
    cover=$COVER
    source=$NOTE
  fi

  case "$backing" in
    http*)
      if ! have_ytdlp; then
        echo "REFUSE  $id: the backing is a URL and yt-dlp is not installed"
        continue
      fi
      ;;
    *)
      [ -f "$backing" ] || { echo "REFUSE  $id: backing '$backing' is not a file"; continue; }
      ;;
  esac
  [ -f "$lyrics" ] || { echo "REFUSE  $id: lyrics '$lyrics' is not a file"; continue; }
  [ -n "${cover:-}" ] || { echo "REFUSE  $id: the queue row needs a cover source"; continue; }
  [ -f "$cover" ] || { echo "REFUSE  $id: cover '$cover' is not a file"; continue; }

  if [ "$DRY" = 1 ]; then
    echo "WOULD   $id: $title — $artist, licence $recorded"
    count=$((count + 1))
    continue
  fi

  echo "=== $id: $title — $artist (licence $recorded)"
  song="$WORK/$id"
  rm -rf "$song"
  started=$(date +%s)
  last=$started
  step() {
    now=$(date +%s)
    echo "  [$((now - last))s] $1"
    last=$now
  }

  kara new "$id" --title "$title" --artist "$artist" \
    --licence "$recorded" --note "$source" --dir "$WORK" >/dev/null
  step new

  kara audio "$backing" --song "$song" || { echo "FAILED  $id: audio"; rm -f "$rows"; exit 1; }
  step audio

  case "$lyrics" in
    *.lrc) kara lyrics "$song" --lrc "$lyrics" --lint ;;
    *.srt) kara lyrics "$song" --srt "$lyrics" --lint ;;
    *) echo "FAILED  $id: '$lyrics' is neither .lrc nor .srt"; rm -f "$rows"; exit 1 ;;
  esac || { echo "FAILED  $id: lyrics"; rm -f "$rows"; exit 1; }
  step lyrics

  kara cover "$song" --from "$cover" >/dev/null ||
    { echo "FAILED  $id: cover"; rm -f "$rows"; exit 1; }
  step cover

  kara package "$song" || { echo "FAILED  $id: package"; rm -f "$rows"; exit 1; }
  step package

  kara publish "$song" --repo "$ROOT" ||
    { echo "FAILED  $id: publish"; rm -f "$rows"; exit 1; }
  step publish

  total=$(( $(date +%s) - started ))
  printf '%s,%s,%s\n' "$id" "$total" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ROOT/songs/times.csv"
  echo "PUBLISHED $id in ${total}s"
  count=$((count + 1))
done < "$rows"

rm -f "$rows"
exit 0
