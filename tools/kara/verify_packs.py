#!/usr/bin/env python
"""Re-downloads packs from the public CDN and checks them against index.json.

    python tools/kara/verify_packs.py                 # three, chosen at random
    python tools/kara/verify_packs.py --count 5
    python tools/kara/verify_packs.py --id shenandoah

This is the only check that proves the *published* catalogue, because it fetches
what a device fetches: jsDelivr, not the local working tree. A pack that the
index describes but the CDN does not serve is a broken install for every player,
and nothing local would show it.
"""
import argparse
import hashlib
import json
import random
import sys
import urllib.error
import urllib.request

CDN = "https://cdn.jsdelivr.net/gh/stevennt/abn.platform.entertainment.karaoke.songs@main"
UA = "ABN-Karaoke/1.0 (contact@abnasia.org)"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def purge(url):
    """Asks jsDelivr to drop its copy of [url].

    A freshly published pack can answer 403 until jsDelivr has fetched it; the
    file is on GitHub and serves fine from raw.githubusercontent.com. Purging is
    the documented way to force the fetch. Returns True when the purge service
    accepted the request.
    """
    import time

    target = url.replace(
        "https://cdn.jsdelivr.net/gh/", "https://purge.jsdelivr.net/gh/"
    )
    try:
        body = fetch(target)
    except Exception:  # noqa: BLE001 - a failed purge is reported by the retry
        return False
    time.sleep(3)
    return b"finished" in body


def fetch_with_purge(url):
    """Fetches [url], purging once and retrying on a 403.

    The double meaning of 403 is the problem: it can be "cold cache" (harmless,
    fixed by a purge) or "not there" (a real break). One retry after a purge
    separates them, and the caller is told which happened.
    """
    try:
        return fetch(url), False
    except urllib.error.HTTPError as error:
        if error.code != 403:
            raise
        if not purge(url):
            raise
        return fetch(url), True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--index", default=f"{CDN}/index.json")
    args = parser.parse_args()

    index = json.loads(fetch(args.index))
    songs = index["songs"]
    if args.id:
        chosen = [s for s in songs if s["id"] in args.id]
        missing = set(args.id) - {s["id"] for s in chosen}
        if missing:
            raise SystemExit(f"not in the index: {', '.join(sorted(missing))}")
    else:
        chosen = random.sample(songs, min(args.count, len(songs)))

    bad = 0
    for song in chosen:
        url = f"{CDN}/{song['pack']['path']}"
        try:
            body, purged = fetch_with_purge(url)
        except urllib.error.HTTPError as error:
            print(f"BROKEN  {song['id']}: {error.code} for {url}")
            bad += 1
            continue
        digest = hashlib.sha256(body).hexdigest()
        want_sha = song["pack"]["sha256"]
        want_bytes = song["pack"]["bytes"]
        ok = digest == want_sha and len(body) == want_bytes
        if purged:
            print(f"  (cold cache: {song['id']} needed a jsDelivr purge)")
        print(
            f"{'OK     ' if ok else 'BROKEN '} {song['id']:<16} "
            f"bytes={len(body):>8} want={want_bytes:>8} "
            f"sha256={digest[:16]}… want={want_sha[:16]}…"
        )
        if not ok:
            bad += 1

    print(f"\n{len(chosen) - bad}/{len(chosen)} verified from {CDN}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
