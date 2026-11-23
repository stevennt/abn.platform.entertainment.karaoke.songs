# Karaoke song library (private)

Package folders and one index for the ABN Asia karaoke app
(`stevennt/abn.platform.entertainment.karaoke`). **Private** until the licences in it have been
cleared for distribution; the app plays everything from local folders and never needs this repo to
sing.

## Layout

```
index.json          every song the app can list: id, title, artist, language,
                    durationMs, bpm, key, difficulty, mode, assets (path +
                    sha256 + bytes), licence, private, updated
songs/<id>/         one package, exactly as docs/SONG-FORMAT.md defines it
  manifest.json
  lyrics.json
  melody.json?      present only when the song is scoreable (`mode: full`)
  cover.webp
  CREDITS.txt
  audio/backing.m4a
  audio/guide.m4a?  guide vocal, when the source has one
```

The folder name, `manifest.id` and the index entry's `id` are the same string.

## Licence policy

Every manifest carries `license: {type, note}`. Accepted types are the app's own list:
`owned`, `public-domain`, `cc-by`, `user-import`. `note` says where the file came from and who to
credit. A song with no recorded licence does not belong in this repo.

`private: true` in the index means the entry is for our own testing and must not be published to
the app's catalogue until a human has checked it.

## How songs get here

The `kara` CLI in the app repo writes and validates packages, then publishes them:

```
cd ~/Workspace/abn.platform.entertainment.karaoke/app
dart run tool/kara/main.dart new <id> --title "…" --artist "…" --licence <type>
dart run tool/kara/main.dart verify ~/.kara/work/<id>
# … audio, lyrics, cover …
dart run tool/kara/main.dart report ~/.kara/work
```

Validation is the app's own loader, so a package that passes `verify` is one the app can open.
Publishing (issue #36) adds the entry to `index.json` and pushes.

## Status

- 2026-11-23 — repo created empty by issue #32.
- 2026-11-23 — the three ABN Asia originals published by issue #37: `spotlight`,
  `one-more-song`, `neon-night`. All `owned`, all `full` (with melodies), all `private: true` until
  a human clears them for the app catalogue.
