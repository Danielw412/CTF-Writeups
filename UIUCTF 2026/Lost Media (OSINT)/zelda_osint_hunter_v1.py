#!/usr/bin/env python3
"""
Search YouTube videos and their available English captions for a fuzzy phrase.

Designed for OSINT/CTF work where you have only a remembered/screenshot caption,
for example:
    "wise men sealed them and the sacred realm now called"

Requirements:
    pip install -U yt-dlp

Examples:
    zelda_osint_hunter_v1.py
    zelda_osint_hunter_v1.py --results-per-query 50 --top 25
    zelda_osint_hunter_v1.py --phrase "wise men sealed them and the sacred realm now called"
    zelda_osint_hunter_v1.py --cookies-from-browser chrome
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

try:
    import yt_dlp
except ImportError:
    print("Missing dependency: yt-dlp")
    print("Install it with:  pip install -U yt-dlp")
    raise SystemExit(1)


DEFAULT_PHRASE = "wise men sealed them and the sacred realm now called"

DEFAULT_QUERIES = [
    "A Link to the Past retrospective",
    "A Link to the Past anniversary",
    "A Link to the Past 20th anniversary",
    "A Link to the Past 25th anniversary",
    "A Link to the Past 30th anniversary",
    "Zelda retrospective A Link to the Past",
    "A Link to the Past review years later",
    "A Link to the Past history",
]

KEYWORDS = [
    "wise men",
    "sacred realm",
    "sealed",
    "seal",
    "dark world",
    "golden land",
    "ganon",
    "ganondorf",
]

ANNIVERSARY_YEARS = {
    2011, 2012,  # ~20th
    2016, 2017,  # ~25th
    2021, 2022,  # ~30th
}


@dataclass
class CaptionLine:
    start: float
    text: str


@dataclass
class Match:
    score: float
    fuzzy: float
    keyword_score: float
    anniversary_bonus: float
    video_id: str
    title: str
    uploader: str
    upload_date: str
    url: str
    timestamp: float
    excerpt: str
    subtitle_kind: str


def normalize_text(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\{\\an\d+\}", " ", s)
    s = s.replace("♪", " ")
    s = s.lower()
    s = re.sub(r"[^a-z0-9'\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_timestamp(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except ValueError:
        pass
    return 0.0


def parse_vtt(path: Path) -> list[CaptionLine]:
    """
    Parse VTT loosely. Deduplicates YouTube's rolling caption lines.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[CaptionLine] = []
    current_start = 0.0
    last_norm = ""

    for line in raw:
        line = line.strip()
        if not line or line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
            continue

        if "-->" in line:
            left = line.split("-->", 1)[0].strip()
            current_start = parse_timestamp(left)
            continue

        if line.isdigit():
            continue

        clean = re.sub(r"<[^>]+>", "", line)
        clean = html.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        norm = normalize_text(clean)

        if not norm:
            continue

        # YouTube auto-captions often repeat/extend previous lines.
        if norm == last_norm:
            continue

        out.append(CaptionLine(current_start, clean))
        last_norm = norm

    return out


def windows(lines: list[CaptionLine], min_words: int = 6, max_words: int = 22) -> Iterable[tuple[float, str]]:
    """
    Yield caption windows roughly comparable in length to the target phrase.
    """
    n = len(lines)
    for i in range(n):
        parts = []
        count = 0
        start = lines[i].start

        for j in range(i, min(n, i + 8)):
            parts.append(lines[j].text)
            count = len(normalize_text(" ".join(parts)).split())
            if count >= min_words:
                yield start, " ".join(parts)
            if count >= max_words:
                break


def score_window(text: str, target: str) -> tuple[float, float]:
    nt = normalize_text(text)
    target_n = normalize_text(target)

    if not nt:
        return 0.0, 0.0

    fuzzy = SequenceMatcher(None, target_n, nt).ratio()

    present = 0
    weighted = 0.0
    for kw in KEYWORDS:
        if kw in nt:
            present += 1
            weighted += 1.4 if " " in kw else 1.0

    keyword_score = min(1.0, weighted / 5.0)

    # Phrase overlap: target words found in candidate.
    target_words = set(target_n.split())
    cand_words = set(nt.split())
    overlap = len(target_words & cand_words) / max(1, len(target_words))

    # Fuzzy is most important, but keyword + token overlap help when captions differ.
    combined = 0.60 * fuzzy + 0.25 * keyword_score + 0.15 * overlap
    return combined, fuzzy


def format_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def ydl_opts_base(cookies_from_browser: str | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": False,
        "skip_download": True,
        "socket_timeout": 20,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def search_videos(queries: list[str], per_query: int, cookies_from_browser: str | None) -> list[dict]:
    seen = set()
    videos = []

    opts = ydl_opts_base(cookies_from_browser)
    # Flat search is faster; we'll get full metadata when downloading subtitles.
    opts["extract_flat"] = "in_playlist"

    with yt_dlp.YoutubeDL(opts) as ydl:
        for q in queries:
            print(f"[search] {q}", file=sys.stderr)
            try:
                info = ydl.extract_info(f"ytsearch{per_query}:{q}", download=False)
            except Exception as e:
                print(f"  search failed: {e}", file=sys.stderr)
                continue

            if not info:
                continue

            for entry in info.get("entries") or []:
                if not entry:
                    continue
                vid = entry.get("id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                videos.append(entry)

    return videos


def choose_subtitle_files(tmp: Path, video_id: str) -> list[Path]:
    candidates = list(tmp.glob(f"*{video_id}*.vtt"))
    if not candidates:
        candidates = list(tmp.glob("*.vtt"))
    return candidates


def fetch_subtitles(video_url: str, video_id: str, tmp: Path, cookies_from_browser: str | None):
    """
    Try manual and auto English subtitles. Returns (metadata, files).
    """
    outtmpl = str(tmp / "%(title).120B [%(id)s].%(ext)s")

    opts = ydl_opts_base(cookies_from_browser)
    opts.update({
        "outtmpl": outtmpl,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB", "en-orig"],
        "subtitlesformat": "vtt",
        "overwrites": True,
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
    except Exception as e:
        return None, [], str(e)

    files = choose_subtitle_files(tmp, video_id)
    return info, files, None


def detect_kind(path: Path) -> str:
    name = path.name.lower()
    if "orig" in name:
        return "manual/original"
    if "en-us" in name or "en-gb" in name or ".en." in name:
        return "English captions"
    return "caption"


def process_video(entry: dict, target: str, cookies_from_browser: str | None, delay: float) -> list[Match]:
    video_id = entry.get("id") or ""
    if not video_id:
        return []

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory(prefix="ytcaption_") as d:
        tmp = Path(d)
        info, files, err = fetch_subtitles(url, video_id, tmp, cookies_from_browser)

        if err:
            print(f"[skip] {video_id}: {err}", file=sys.stderr)
            return []

        if not info or not files:
            return []

        title = info.get("title") or entry.get("title") or video_id
        uploader = info.get("uploader") or info.get("channel") or "?"
        upload_date = info.get("upload_date") or ""
        year = None
        if len(upload_date) >= 4 and upload_date[:4].isdigit():
            year = int(upload_date[:4])

        anniversary_bonus = 0.06 if year in ANNIVERSARY_YEARS else 0.0
        found: list[Match] = []

        for subfile in files:
            try:
                lines = parse_vtt(subfile)
            except Exception:
                continue

            best = None
            for ts, excerpt in windows(lines):
                combined, fuzzy = score_window(excerpt, target)
                total = min(1.0, combined + anniversary_bonus)

                if best is None or total > best[0]:
                    keyword_hits = sum(1 for kw in KEYWORDS if kw in normalize_text(excerpt))
                    best = (total, fuzzy, keyword_hits, ts, excerpt)

            if best:
                total, fuzzy, keyword_hits, ts, excerpt = best
                found.append(Match(
                    score=total,
                    fuzzy=fuzzy,
                    keyword_score=keyword_hits / len(KEYWORDS),
                    anniversary_bonus=anniversary_bonus,
                    video_id=video_id,
                    title=title,
                    uploader=uploader,
                    upload_date=upload_date,
                    url=url,
                    timestamp=ts,
                    excerpt=re.sub(r"\s+", " ", excerpt).strip(),
                    subtitle_kind=detect_kind(subfile),
                ))

        if delay:
            time.sleep(delay)

        return found


def main():
    ap = argparse.ArgumentParser(
        description="Search YouTube captions and fuzzy-match a remembered phrase."
    )
    ap.add_argument(
        "--phrase",
        default=DEFAULT_PHRASE,
        help=f'Phrase to fuzzy-match (default: "{DEFAULT_PHRASE}")',
    )
    ap.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="YouTube search query. May be given multiple times. Defaults to Zelda anniversary searches.",
    )
    ap.add_argument(
        "--results-per-query",
        type=int,
        default=30,
        help="YouTube results to collect per search query (default: 30).",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=30,
        help="How many ranked matches to print (default: 30).",
    )
    ap.add_argument(
        "--min-score",
        type=float,
        default=0.30,
        help="Suppress matches below this score, from 0 to 1 (default: 0.30).",
    )
    ap.add_argument(
        "--cookies-from-browser",
        choices=["chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium"],
        help="Use browser cookies if YouTube blocks/rate-limits anonymous requests.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay between videos in seconds (default: 0.25).",
    )
    ap.add_argument(
        "--json",
        dest="json_path",
        help="Also write ranked results as JSON to this path.",
    )
    args = ap.parse_args()

    queries = args.queries or DEFAULT_QUERIES

    print(f"Target phrase: {args.phrase}", file=sys.stderr)
    print(f"Searching {len(queries)} queries × up to {args.results_per_query} results...", file=sys.stderr)

    videos = search_videos(queries, args.results_per_query, args.cookies_from_browser)
    print(f"Unique candidate videos: {len(videos)}", file=sys.stderr)

    all_matches: list[Match] = []

    for idx, entry in enumerate(videos, 1):
        title = entry.get("title") or entry.get("id") or "?"
        print(f"[{idx}/{len(videos)}] {title[:90]}", file=sys.stderr)
        matches = process_video(entry, args.phrase, args.cookies_from_browser, args.delay)
        all_matches.extend(matches)

    # One best subtitle track per video.
    best_by_video: dict[str, Match] = {}
    for m in all_matches:
        old = best_by_video.get(m.video_id)
        if old is None or m.score > old.score:
            best_by_video[m.video_id] = m

    ranked = sorted(best_by_video.values(), key=lambda m: m.score, reverse=True)
    ranked = [m for m in ranked if m.score >= args.min_score]

    print()
    print("=" * 100)
    print(f"TOP MATCHES for: {args.phrase!r}")
    print("=" * 100)

    if not ranked:
        print("No matches above threshold.")
        print("Try: --min-score 0.20, larger --results-per-query, or --cookies-from-browser chrome")
        return

    for i, m in enumerate(ranked[: args.top], 1):
        date = m.upload_date or "unknown-date"
        date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
        link = f"{m.url}&t={int(m.timestamp)}s"

        print(f"\n#{i}  SCORE {m.score:.3f}   fuzzy={m.fuzzy:.3f}"
              f"   anniversary_bonus={m.anniversary_bonus:.2f}")
        print(f"Title:    {m.title}")
        print(f"Channel:  {m.uploader}")
        print(f"Date:     {date_fmt}")
        print(f"At:       {format_ts(m.timestamp)}")
        print(f"URL:      {link}")
        print(f"Captions: {m.subtitle_kind}")
        print(f"Excerpt:  {m.excerpt[:500]}")

    if args.json_path:
        data = [
            {
                "score": m.score,
                "fuzzy": m.fuzzy,
                "anniversary_bonus": m.anniversary_bonus,
                "video_id": m.video_id,
                "title": m.title,
                "uploader": m.uploader,
                "upload_date": m.upload_date,
                "url": f"{m.url}&t={int(m.timestamp)}s",
                "timestamp_seconds": m.timestamp,
                "timestamp": format_ts(m.timestamp),
                "excerpt": m.excerpt,
                "subtitle_kind": m.subtitle_kind,
            }
            for m in ranked[: args.top]
        ]
        Path(args.json_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\nWrote JSON results to {args.json_path}")


if __name__ == "__main__":
    main()
