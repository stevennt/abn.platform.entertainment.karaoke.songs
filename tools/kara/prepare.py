#!/usr/bin/env python
"""Turns a public-domain recording into the three files `kara` needs.

    python tools/kara/prepare.py shenandoah

Reads `songs/sources/<id>.json`, downloads the Commons file, refuses it unless
its licence is public domain or CC0, separates the vocal with demucs (the
backing must not carry the singer, or the karaoke is unusable), transcribes the
vocal with Whisper for *timings only*, distributes the real lyric lines across
those timings, then writes a deterministic cover.

It prints `KEY=value` lines and also writes them to
`.work/src/<id>/vars.sh`, so `batch.sh` can source them and keep doing the
`new → audio → lyrics → cover → package → publish` steps itself.

Nothing is published here. Separation and transcription are the only costly
parts, and both are skipped when their output already exists — a re-run after a
failure resumes instead of repeating ten minutes of work.

The licence refusal is the point: the catalogue is public, so a recording whose
rights cannot be stated must never reach a package.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.path.join(ROOT, ".work", "src")
API = "https://commons.wikimedia.org/w/api.php"
UA = "ABN-Karaoke/1.0 (contact@abnasia.org)"
FREE = (
    "public domain",
    "cc0",
    "cc by 1.0",
    "cc by 2.0",
    "cc by 2.5",
    "cc by 3.0",
    "cc by 4.0",
    "cc by-sa 1.0",
    "cc by-sa 2.0",
    "cc by-sa 2.5",
    "cc by-sa 3.0",
    "cc by-sa 4.0",
)


def say(message):
    sys.stderr.write(f"  {message}\n")


def api(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def plain(html):
    return re.sub(r"<[^>]*>", "", html or "").strip()


def record(spec):
    """The Commons file's url, licence and a human credit line."""
    time.sleep(1)
    data = api(
        {
            "action": "query",
            "titles": spec["commons_title"],
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }
    )
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise SystemExit(f"no such Commons file: {spec['commons_title']}")
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        raise SystemExit(f"no image info for {spec['commons_title']}")
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    return {
        "url": info["url"].split("?")[0],
        "bytes": info.get("size"),
        "mime": info.get("mime"),
        "licence": plain((meta.get("LicenseShortName", {}) or {}).get("value")),
        "licence_url": plain((meta.get("LicenseUrl", {}) or {}).get("value")),
        "artist": plain((meta.get("Artist", {}) or {}).get("value")),
        "credit": plain((meta.get("Credit", {}) or {}).get("value")),
        "page": f"https://commons.wikimedia.org/wiki/"
        + urllib.parse.quote(spec["commons_title"].replace(" ", "_")),
    }


def run(argv, what, timeout=None):
    started = time.time()
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"{what} ran past {timeout}s and was stopped")
    if done.returncode != 0:
        sys.stderr.write(done.stderr[-1500:])
        raise SystemExit(f"{what} failed ({done.returncode})")
    return time.time() - started


def srt_segments(path):
    blocks = [b for b in open(path).read().strip().split("\n\n") if b.strip()]
    out = []
    for block in blocks:
        lines = block.split("\n")
        stamp = re.search(
            r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", block
        )
        if not stamp:
            continue
        h1, m1, s1, f1, h2, m2, s2, f2 = (int(g) for g in stamp.groups())
        start = ((h1 * 60 + m1) * 60 + s1) * 1000 + f1
        end = ((h2 * 60 + m2) * 60 + s2) * 1000 + f2
        text = " ".join(lines[2:]).strip()
        if text and end > start:
            out.append((start, end, text))
    return out


def distribute(lines, segments):
    """Places each lyric line in time, inside the transcribed segments.

    Whisper gives where singing happens; the lyric file gives what is said. The
    lines are spread across the segments in proportion to how long each one
    lasts, which keeps a line from landing in an instrumental gap.
    """
    total = sum(end - start for start, end, _ in segments)
    if total <= 0:
        raise SystemExit("the transcript has no timed segments")
    counts = []
    remaining = len(lines)
    for index, (start, end, _) in enumerate(segments):
        if index == len(segments) - 1:
            counts.append(remaining)
        else:
            share = round(len(lines) * (end - start) / total)
            share = max(1, min(share, remaining - (len(segments) - index - 1)))
            counts.append(share)
            remaining -= share
    placed = []
    cursor = 0
    for (start, end, _), count in zip(segments, counts):
        step = (end - start) / max(1, count)
        for index in range(count):
            if cursor >= len(lines):
                break
            placed.append((int(start + index * step), lines[cursor]))
            cursor += 1
    while cursor < len(lines):
        placed.append((placed[-1][0] if placed else 0, lines[cursor]))
        cursor += 1
    return placed


def audio_duration_ms(path):
    done = subprocess.run(
        ["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise SystemExit(f"ffprobe could not read {path}")
    return int(float(done.stdout.strip()) * 1000)


def stamp(ms):
    total = ms / 1000
    return f"{int(total // 60):02d}:{total % 60:05.2f}"


def cover(spec, path, size=1440):
    from PIL import Image, ImageDraw

    ink = (11, 11, 14)
    tint = tuple(int(spec.get("tint", "#E8A33D")[i : i + 2], 16) for i in (1, 3, 5))
    seed = int(hashlib.sha256(spec["id"].encode()).hexdigest()[:8], 16)
    image = Image.new("RGB", (size, size), ink)
    pixels = image.load()
    cx = size * (0.36 + (seed % 29) / 100)
    cy = size * (0.38 + (seed % 17) / 100)
    reach = size * 0.78
    for y in range(size):
        for x in range(size):
            dx = (x - cx) / reach
            dy = (y - cy) / reach
            distance = dx * dx + dy * dy
            if distance >= 1:
                continue
            strength = (1 - distance) ** 2 * 0.5
            pixels[x, y] = tuple(
                round(ink[i] + (tint[i] - ink[i]) * strength) for i in range(3)
            )
    draw = ImageDraw.Draw(image)
    notes = (seed % 3) + 3
    for index in range(notes):
        nx = 0.22 + index * (0.56 / notes)
        ny = 0.62 - index * 0.045
        radius = size * 0.042
        draw.ellipse(
            [nx * size - radius, ny * size - radius, nx * size + radius, ny * size + radius],
            fill=tint,
        )
        draw.rectangle(
            [nx * size + radius * 0.7, ny * size - radius * 5,
             nx * size + radius * 1.3, ny * size],
            fill=tint,
        )
    draw.rectangle(
        [size * 0.06, size * 0.92, size * 0.06 + size * 0.16, size * 0.92 + 4],
        fill=tint,
    )
    image.save(path)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare.py <id>")
    song_id = sys.argv[1]
    spec_path = os.path.join(ROOT, "songs", "sources", f"{song_id}.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"no source spec at {spec_path}")
    spec = json.load(open(spec_path))
    spec.setdefault("id", song_id)

    out = os.path.join(WORK, song_id)
    os.makedirs(out, exist_ok=True)
    marks = {}

    info = record(spec)
    licence = info["licence"].lower()
    if not any(licence.startswith(prefix) for prefix in FREE):
        raise SystemExit(
            f"REFUSED {song_id}: '{info['licence']}' is not a free licence "
            f"({info['page']})"
        )
    marks["licence"] = f"{info['licence']} — {info['page']}"

    source = os.path.join(out, "source")
    if not os.path.exists(source):
        say(f"downloading {info['bytes'] / 1e6:.1f} MB")
        time.sleep(1)
        request = urllib.request.Request(info["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            open(source, "wb").write(response.read())
        say(f"downloaded in one piece: {os.path.getsize(source)} bytes")

    wav = os.path.join(out, "work.wav")
    if not os.path.exists(wav):
        marks["convert"] = round(
            run(
                ["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-i", source,
                 "-ar", "44100", "-ac", "1", wav],
                "ffmpeg",
            ),
            1,
        )
        say(f"converted in {marks['convert']}s")

    backing = os.path.join(out, "htdemucs", "work", "no_vocals.mp3")
    vocals = os.path.join(out, "htdemucs", "work", "vocals.mp3")
    if not os.path.exists(backing):
        venv = os.path.dirname(sys.executable)
        marks["separate"] = round(
            run(
                [os.path.join(venv, "python"), "-m", "demucs", "--two-stems=vocals",
                 "-n", "htdemucs", "--mp3", "-o", out, wav],
                "demucs",
            ),
            1,
        )
        say(f"separated in {marks['separate']}s")
    if not os.path.exists(backing):
        raise SystemExit(f"demucs produced no backing for {song_id}")

    srt = os.path.join(out, "vocals.srt")
    if not os.path.exists(srt):
        marks["transcribe"] = round(
            run(
                ["/opt/homebrew/bin/whisper", vocals, "--model", spec.get("model", "small.en"),
                 "--language", spec.get("language", "en"), "--output_format", "srt",
                 "--output_dir", out, "--verbose", "False"],
                "whisper",
                timeout=max(300, int(audio_duration_ms(vocals) / 1000 * 3)),
            ),
            1,
        )
        produced = os.path.join(out, "vocals.srt")
        if not os.path.exists(produced):
            raise SystemExit(f"whisper produced no transcript for {song_id}")
        say(f"transcribed in {marks['transcribe']}s")

    lyrics = [line.strip() for line in spec["lyrics"] if line.strip()]
    duration_ms = audio_duration_ms(backing)
    segments = []
    for start, end, text in srt_segments(srt):
        if start >= duration_ms:
            say(f"dropping a segment at {start}ms, past the {duration_ms}ms recording")
            continue
        segments.append((start, min(end, duration_ms), text))
    if not segments:
        raise SystemExit(f"the transcript for {song_id} is empty")
    placed = distribute(lyrics, segments)
    ceiling = duration_ms - 500
    clamped = []
    previous = -1
    for ms, text in placed:
        ms = min(ms, ceiling)
        if ms <= previous:
            ms = previous + 1
        previous = ms
        clamped.append((ms, text))
    if clamped and clamped[-1][0] >= duration_ms:
        raise SystemExit(f"the lyric sheet for {song_id} does not fit the recording")
    placed = clamped
    lrc = os.path.join(out, "lyrics.lrc")
    with open(lrc, "w") as handle:
        handle.write(f"[ti:{spec['title']}]\n[ar:{spec.get('artist', 'Traditional')}]\n")
        for ms, text in placed:
            handle.write(f"[{stamp(ms)}]{text}\n")
    marks["lines"] = len(placed)
    marks["segments"] = len(segments)

    art = os.path.join(out, "cover.png")
    if not os.path.exists(art):
        cover(spec, art)

    credit = spec["credit"].rstrip()
    note = (
        f"Composition: {spec['composition']}. "
        f"Recording: {info['artist'] or spec.get('performer', 'unknown')}, "
        f"{info['licence']} ({info['page']}); backing separated with demucs, "
        f"lyric timings derived from the recording. {credit}"
    )
    os.makedirs(os.path.join(WORK, song_id), exist_ok=True)
    with open(os.path.join(out, "vars.sh"), "w") as handle:
        for key, value in (
            ("BACKING", backing),
            ("LYRICS", lrc),
            ("COVER", art),
            ("NOTE", note),
            ("LICENCE_NAME", info["licence"]),
            ("SOURCE_PAGE", info["page"]),
        ):
            handle.write(f"{key}={json.dumps(value)}\n")

    print(f"PREPARED {song_id} licence={info['licence']} lines={marks['lines']} "
          f"segments={marks['segments']} "
          + " ".join(f"{k}={v}s" for k, v in marks.items() if isinstance(v, (int, float))))


if __name__ == "__main__":
    main()
