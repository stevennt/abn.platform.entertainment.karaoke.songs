# index.json — one entry per song, written by `kara publish` (#36).

Entry shape (documented here so the CLI and the app cannot drift):

```json
{
  "id": "spotlight",
  "title": "Spotlight",
  "artist": "ABN Asia",
  "language": "en",
  "durationMs": 61400,
  "bpm": 96,
  "key": "C",
  "difficulty": 2,
  "mode": "full",
  "assets": {
    "backing": {"path": "songs/spotlight/audio/backing.m4a", "sha256": "…", "bytes": 0},
    "lyrics":  {"path": "songs/spotlight/lyrics.json",       "sha256": "…", "bytes": 0},
    "melody":  {"path": "songs/spotlight/melody.json",       "sha256": "…", "bytes": 0},
    "cover":   {"path": "songs/spotlight/cover.webp",        "sha256": "…", "bytes": 0}
  },
  "pack": {"path": "packs/spotlight-<sha-prefix>.zip", "sha256": "…", "bytes": 0},
  "licence": {"type": "owned", "note": "ABN Asia original composition and recording"},
  "private": true,
  "updated": "2026-11-23"
}
```

Rules:

- `mode` is the package's own `capabilities.mode` — `full` only when `melody.json` exists.
- `melody` is omitted for a `lyrics-only` song; nothing may invent it.
- `sha256` is of the file as stored, lowercase hex; `bytes` is its size.
- `private: true` until a human has cleared the licence for distribution.
- `format` at the top of the file is the index schema version, not a song's.
