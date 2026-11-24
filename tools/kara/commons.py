#!/usr/bin/env python
"""Finds public-domain / freely licensed recordings on Wikimedia Commons.

Reading only; it downloads nothing. Prints one line per candidate so a song can
be chosen with its licence visible, which is the whole point: the catalogue is
public, so the right on the recording has to be stated before anything ships.

    python tools/kara/commons.py "Amazing Grace" "Auld Lang Syne"
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "ABN-Karaoke/1.0 (contact@abnasia.org)"


def get(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def candidates(term, limit=6):
    time.sleep(1.5)
    found = get(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"filetype:audio {term}",
            "srnamespace": "6",
            "srlimit": str(limit),
        }
    )
    titles = [r["title"] for r in found.get("query", {}).get("search", [])]
    if not titles:
        return []
    time.sleep(1.5)
    info = get(
        {
            "action": "query",
            "titles": "|".join(titles),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }
    )
    rows = []
    for page in info.get("query", {}).get("pages", {}).values():
        for item in page.get("imageinfo", []):
            meta = item.get("extmetadata", {})
            rows.append(
                {
                    "title": page["title"],
                    "url": item.get("url", "").split("?")[0],
                    "mb": round((item.get("size") or 0) / 1_000_000, 1),
                    "licence": (meta.get("LicenseShortName", {}) or {}).get("value", ""),
                    "artist": _plain((meta.get("Artist", {}) or {}).get("value", ""))[:40],
                }
            )
    return rows


def _plain(html):
    out, depth = [], 0
    for ch in html:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out).strip()


def main():
    for term in sys.argv[1:]:
        print(f"=== {term}")
        try:
            rows = candidates(term)
        except Exception as error:  # noqa: BLE001 - a search failure is not fatal
            print(f"    search failed: {error}")
            continue
        for row in rows:
            print(
                f"  {row['title'][5:][:60]:<60} {row['mb']:5.1f}MB "
                f"{row['licence'][:20]:<20} {row['artist']}"
            )


if __name__ == "__main__":
    main()
