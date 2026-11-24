# Karaoke song library

Packages and one index for the ABN Asia karaoke app
(`stevennt/abn.platform.entertainment.karaoke`). **Public since 2026-11-24**: the app lists these
songs from the index below and downloads a pack when someone chooses it. The app also sings entirely
from local folders, so this repo is a shelf, not a dependency.

## The catalogue URL

```
https://cdn.jsdelivr.net/gh/stevennt/abn.platform.entertainment.karaoke.songs@main/index.json
```

A build points at it with:

```
flutter build apk --release \
  --dart-define=KARAOKE_CATALOGUE_URL=https://cdn.jsdelivr.net/gh/stevennt/abn.platform.entertainment.karaoke.songs@main/index.json
```

jsDelivr serves files up to **20 MB**. A pack larger than that lives in Cloudflare R2 and its index
entry points at the R2 URL; the `pack.bytes` figure says which.

## Layout

```
index.json          every song the app can list: id, title, artist, language,
                    durationMs, bpm, key, difficulty, mode, assets (path +
                    sha256 + bytes), pack, licence, private, updated
songs/<id>/         one package, exactly as docs/SONG-FORMAT.md defines it
  manifest.json
  lyrics.json
  melody.json?      present only when the song is scoreable (`mode: full`)
  cover.webp
  CREDITS.txt
  audio/backing.m4a
  audio/guide.m4a?  guide vocal, when the source has one
packs/              deterministic zips: <id>-<sha8>.zip
```

The folder name, `manifest.id` and the index entry's `id` are the same string.

## Licence policy

**Every song carries a licence, and the index repeats it.** Accepted types are the app's own list:

| type | meaning |
|---|---|
| `owned` | composed and recorded by ABN Asia, or assigned to it in writing |
| `public-domain` | the composition is out of copyright **and** the recording is ours |
| `cc-by` | Creative Commons Attribution, with the attribution in `CREDITS.txt` |
| `user-import` | someone's own recording, added through the app |

A song with no recorded licence **does not belong in this repo**. `kara publish` refuses a package
that has none, and the index carries the same block so a reader never has to open the zip.

`private: true` on an index entry is the deliberate exception — a song kept in the repo with its
licence recorded but held back from the catalogue. `kara publish --hold-back` sets it.

## Producing songs in bulk

`tools/kara/batch.sh` works a queue, one song at a time, and refuses anything that
is not licensed:

```bash
tools/kara/batch.sh --dry-run     # say what would happen, change nothing
tools/kara/batch.sh --limit 2     # stop after two
tools/kara/batch.sh               # the whole queue
```

| File | What it is |
|---|---|
| `songs/queue.csv` | the work: `id,title,artist,backing,lyrics,cover,licence,source` |
| `songs/licenses.csv` | the ledger: `id,licence,note`, written **before** a package is built |
| `songs/times.csv` | one line per published song: id, wall-clock seconds, when |

**Resumable.** A row whose id is already in `index.json` is `SKIP`ped, so a run
that dies at song seven can be started again and continues at seven.

**Refusing is the normal case.** Before any work the runner stops on: no ledger
row, a licence outside the four accepted types, a queue licence that disagrees
with the ledger, a missing backing or lyrics file, a URL backing while `yt-dlp`
is not installed, or a missing cover source. It prints `REFUSE <id>: <why>` and
carries on to the next row; the first *hard* failure (a step that ran and died)
stops the run with `FAILED <id>: <step>`.

### Sourcing from a public-domain recording

A queue row with `auto` in the `backing` column builds its three inputs from a
recording on Wikimedia Commons, described by `songs/sources/<id>.json`:

```json
{
  "id": "shenandoah",
  "title": "Shenandoah",
  "artist": "Traditional",
  "commons_title": "File:Shenandoah (2017) - Singing Sergeants - United States Air Force Band.mp3",
  "composition": "traditional American folk song; lyrics public domain",
  "credit": "performance by the US Air Force Band (a US Government work)",
  "lyrics": ["Oh Shenandoah, I long to hear you", "..."]
}
```

`tools/kara/prepare.py` then:

1. reads the file's licence from Commons and **refuses anything that is not
   public domain, CC0 or CC-BY** — before the expensive work, not after;
2. downloads it and converts to 44.1 kHz mono;
3. separates the vocal with `demucs` (the backing must not carry the singer);
4. transcribes the vocal with Whisper for **timings only** — the words come from
   the spec, never from the transcript;
5. spreads the real lyric lines across the transcribed segments in proportion to
   their length, so a line cannot land in an instrumental gap;
6. draws a deterministic cover from the song id, so every song gets a different
   one without shipping artwork.

`prepare.py` caches each stage in `.work/src/<id>/`, so a run that dies at
package time resumes at package time. The licence check, the download and the
Whisper pass are all skipped when their output already exists.

Find a recording with `tools/kara/commons.py "<title>"`, which prints candidates
with their licence and size. Choose one whose **recording** is free, not merely
one whose composition is old — a 1911 song in a 2019 recording is not free.

## Adding a song

```bash
# 1. build the package (audio, lyrics, timings, cover, manifest with licence)
cd ~/Workspace/abn.platform.entertainment.karaoke/app
dart run tool/kara/main.dart new  ~/Work/neon-night-2 --title "…" --artist "ABN Asia"
dart run tool/kara/main.dart audio ~/Work/neon-night-2 backing.wav
dart run tool/kara/main.dart lyrics ~/Work/neon-night-2 lyrics.json
dart run tool/kara/main.dart whisper ~/Work/neon-night-2 take.wav
dart run tool/kara/main.dart package ~/Work/neon-night-2

# 2. publish it: builds the deterministic zip, updates index.json, pushes this repo
dart run tool/kara/main.dart publish ~/Work/neon-night-2
```

`publish` refuses a package whose licence is missing or whose assets do not verify, and it never
rewrites an entry whose hash has not changed.

## What is in here now

| id | title | licence |
|---|---|---|
| `neon-night` | Neon Night | owned — original ABN Asia composition and recording |
| `one-more-song` | One More Song | owned — original ABN Asia composition and recording |
| `spotlight` | Spotlight | owned — original ABN Asia composition and recording |

Audio: every backing track is an ABN Asia recording. No third-party master is distributed here.
