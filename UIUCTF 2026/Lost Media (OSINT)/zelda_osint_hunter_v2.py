#!/usr/bin/env python3
"""
Zelda OSINT Hunter v2
=====================

Purpose
-------
Find the exact YouTube video from a screenshot/clue by using the signals in
the right order:

  1) Search for A Link to the Past retrospective/review/look-back videos.
  2) Rank by proximity to ALttP's 20th/25th/30th anniversaries.
  3) Require the video to be long enough to have an 8:07 timestamp.
  4) Search captions for an ORDERED lore pattern, not generic keyword overlap.
  5) For strong transcript hits, download only a short low-res clip around the
     hit and compare extracted frames against clue.png.
  6) Produce a ranked CSV/JSON/HTML report and contact sheets for manual review.

This does NOT assume the clue screenshot is from 8:07. 8:07 is only the final
verification timestamp after the original video has been identified.

Requirements
------------
    pip install -U yt-dlp pillow numpy

Optional but strongly recommended for visual matching:
    pip install -U opencv-python

You also need ffmpeg on PATH for short-section downloads/frame extraction.

Windows example:
    python zelda_osint_hunter_v2.py --clue clue.png --cookies-from-browser chrome

Safer first pass (metadata + transcripts only):
    python zelda_osint_hunter_v2.py --clue clue.png --no-visual

Broader search:
    python zelda_osint_hunter_v2.py --clue clue.png --results-per-query 50 --transcript-candidates 120

Resume:
    Run the exact same command again. Metadata/transcripts are cached in
    ./zelda_hunt_cache and already-downloaded work is reused.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    import yt_dlp
except ImportError:
    print("Missing dependency: yt-dlp")
    print("Install with: pip install -U yt-dlp")
    raise SystemExit(1)

try:
    import numpy as np
except ImportError:
    print("Missing dependency: numpy")
    print("Install with: pip install -U numpy")
    raise SystemExit(1)

try:
    from PIL import Image, ImageOps, ImageDraw, ImageFont
except ImportError:
    print("Missing dependency: Pillow")
    print("Install with: pip install -U pillow")
    raise SystemExit(1)

try:
    import cv2
except Exception:
    cv2 = None


# ---------------------------------------------------------------------------
# Challenge-specific prior
# ---------------------------------------------------------------------------

# A Link to the Past:
#   JP: 1991-11-21
#   NA: 1992-04-13
# We care about 20th, 25th, and 30th anniversaries.
ANNIVERSARIES = [
    ("20th JP", dt.date(2011, 11, 21)),
    ("20th NA", dt.date(2012, 4, 13)),
    ("25th JP", dt.date(2016, 11, 21)),
    ("25th NA", dt.date(2017, 4, 13)),
    ("30th JP", dt.date(2021, 11, 21)),
    ("30th NA", dt.date(2022, 4, 13)),
]

DEFAULT_QUERIES = [
    '"A Link to the Past" retrospective',
    '"A Link to the Past" review',
    '"A Link to the Past" analysis',
    '"A Link to the Past" history',
    '"A Link to the Past" "look back"',
    '"A Link to the Past" "looking back"',
    '"A Link to the Past" "years later"',
    '"A Link to the Past" anniversary',
    '"A Link to the Past" "20 years later"',
    '"A Link to the Past" "25 years later"',
    '"A Link to the Past" "30 years later"',
    '"Legend of Zelda" "A Link to the Past" retrospective',
    '"Zelda 3" retrospective',
    '"Zelda 3" review',
]

# Things that make a title sound like a retrospective/look-back.
TITLE_POSITIVE = {
    "retrospective": 2.2,
    "review": 1.7,
    "analysis": 1.5,
    "history": 1.3,
    "look back": 2.0,
    "looking back": 2.0,
    "years later": 2.1,
    "year later": 1.8,
    "anniversary": 2.0,
    "remember": 0.8,
    "legacy": 0.8,
    "still": 0.4,
    "defined": 0.6,
    "definitive": 0.5,
    "masterpiece": 0.4,
}

TITLE_NEGATIVE = {
    "let's play": -2.5,
    "lets play": -2.5,
    "playthrough": -2.3,
    "walkthrough": -2.5,
    "speedrun": -3.0,
    "longplay": -3.0,
    "livestream": -2.5,
    "stream": -1.7,
    "soundtrack": -3.0,
    "ost": -2.0,
    "orchestra": -2.5,
    "concert": -2.5,
    "music": -1.3,
    "part 1": -0.5,
    "part 2": -0.5,
    "part 3": -0.5,
    "part 4": -0.5,
    "episode": -0.8,
    "ep.": -0.6,
    "gameplay": -0.7,
}

# The screenshot's caption is approximate. We don't require exact wording.
# Instead we look for a *structural* sequence from the ALttP backstory.
STRICT_PATTERNS = [
    # name, regex components in expected order, base bonus
    (
        "wise-seal-realm-called-dark",
        [
            r"\bwise\b",
            r"\b(?:men|man|sages?)\b",
            r"\bseal(?:ed|ing|s)?\b",
            r"\b(?:sacred\s+realm|golden\s+land)\b",
            r"\b(?:now\s+called|called|known\s+as|became|turned\s+into)\b",
            r"\bdark\s+world\b",
        ],
        10.0,
    ),
    (
        "wise-seal-golden-dark",
        [
            r"\bwise\b",
            r"\b(?:men|man|sages?)\b",
            r"\bseal(?:ed|ing|s)?\b",
            r"\bgolden\s+land\b",
            r"\bdark\s+world\b",
        ],
        8.0,
    ),
    (
        "seal-realm-called-dark",
        [
            r"\bseal(?:ed|ing|s)?\b",
            r"\b(?:sacred\s+realm|golden\s+land)\b",
            r"\b(?:now\s+called|called|known\s+as|became|turned\s+into)\b",
            r"\bdark\s+world\b",
        ],
        7.0,
    ),
    (
        "wise-seal-realm",
        [
            r"\bwise\b",
            r"\b(?:men|man|sages?)\b",
            r"\bseal(?:ed|ing|s)?\b",
            r"\b(?:sacred\s+realm|golden\s+land)\b",
        ],
        5.0,
    ),
    (
        "realm-called-dark",
        [
            r"\b(?:sacred\s+realm|golden\s+land)\b",
            r"\b(?:now\s+called|called|known\s+as|became|turned\s+into)\b",
            r"\bdark\s+world\b",
        ],
        4.0,
    ),
]

FALLBACK_TERMS = [
    ("wise", 1.2),
    ("men", 0.5),
    ("sages", 0.5),
    ("seal", 1.2),
    ("sealed", 1.2),
    ("sacred realm", 1.6),
    ("golden land", 1.5),
    ("dark world", 1.5),
    ("called", 0.6),
    ("known as", 0.6),
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    video_id: str
    title: str = ""
    url: str = ""
    channel: str = ""
    upload_date: str = ""
    duration: Optional[float] = None
    view_count: Optional[int] = None

    nearest_anniversary: str = ""
    anniversary_date: str = ""
    anniversary_days: Optional[int] = None
    date_score: float = 0.0
    title_score: float = 0.0
    metadata_score: float = 0.0

    transcript_score: float = 0.0
    transcript_timestamp: Optional[float] = None
    transcript_pattern: str = ""
    transcript_excerpt: str = ""
    transcript_kind: str = ""

    visual_score: Optional[float] = None
    visual_timestamp: Optional[float] = None
    visual_frame: str = ""

    final_score: float = 0.0
    search_queries: list[str] = field(default_factory=list)


@dataclass
class CaptionLine:
    start: float
    text: str


@dataclass
class TranscriptHit:
    score: float
    timestamp: float
    pattern: str
    excerpt: str


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def safe_filename(s: str, max_len: int = 100) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:max_len] or "untitled").strip()


def normalize_text(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\{\\an\d+\}", " ", s)
    s = s.lower()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^a-z0-9'\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_yyyymmdd(s: str) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:8], "%Y%m%d").date()
    except Exception:
        return None


def fmt_date(s: str) -> str:
    d = parse_yyyymmdd(s)
    return d.isoformat() if d else (s or "unknown")


def fmt_ts(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    sec = max(0, int(round(seconds)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def timestamp_url(url: str, seconds: Optional[float]) -> str:
    if seconds is None:
        return url
    join = "&" if "?" in url else "?"
    return f"{url}{join}t={int(max(0, seconds))}s"


def cache_read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Metadata ranking
# ---------------------------------------------------------------------------

def score_title(title: str) -> float:
    t = normalize_text(title)
    score = 0.0
    for phrase, weight in TITLE_POSITIVE.items():
        if phrase in t:
            score += weight
    for phrase, weight in TITLE_NEGATIVE.items():
        if phrase in t:
            score += weight

    # Strongly prefer a title that is actually about ALttP/Zelda 3.
    if "link to the past" in t:
        score += 2.0
    elif "zelda 3" in t:
        score += 1.3

    # A video called "Part 37" is usually gameplay, but don't hard-reject.
    if re.search(r"\b(?:part|episode|ep)\s*\d+\b", t):
        score -= 0.7

    # Squash to 0..1. We still allow mediocre titles.
    return 1.0 / (1.0 + math.exp(-0.72 * (score - 1.0)))


def nearest_anniversary(upload_date: str) -> tuple[str, str, Optional[int], float]:
    d = parse_yyyymmdd(upload_date)
    if d is None:
        return "", "", None, 0.18  # unknown date: don't kill it

    label, target = min(ANNIVERSARIES, key=lambda x: abs((d - x[1]).days))
    days = abs((d - target).days)

    # Piecewise decay. "Around" is vague, so preserve a long tail.
    if days <= 14:
        score = 1.00
    elif days <= 30:
        score = 0.95
    elif days <= 60:
        score = 0.88
    elif days <= 90:
        score = 0.78
    elif days <= 180:
        score = 0.62
    elif days <= 365:
        score = 0.40
    elif days <= 540:
        score = 0.20
    else:
        score = 0.03

    return label, target.isoformat(), days, score


def compute_metadata_score(c: Candidate) -> None:
    label, adate, days, dscore = nearest_anniversary(c.upload_date)
    c.nearest_anniversary = label
    c.anniversary_date = adate
    c.anniversary_days = days
    c.date_score = dscore
    c.title_score = score_title(c.title)

    # Date is the strongest prior; title is secondary.
    c.metadata_score = 0.67 * c.date_score + 0.33 * c.title_score

    # The challenge explicitly asks about 8:07, so the correct video must reach it.
    if c.duration is not None and c.duration < 487:
        c.metadata_score = 0.0


# ---------------------------------------------------------------------------
# YouTube search and full metadata
# ---------------------------------------------------------------------------

def base_ydl_opts(cookies_from_browser: Optional[str]) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def collect_search_results(
    queries: list[str],
    results_per_query: int,
    cookies_from_browser: Optional[str],
) -> dict[str, Candidate]:
    opts = base_ydl_opts(cookies_from_browser)
    opts.update({
        "extract_flat": "in_playlist",
        "skip_download": True,
    })

    found: dict[str, Candidate] = {}

    with yt_dlp.YoutubeDL(opts) as ydl:
        for q in queries:
            eprint(f"[search] {q}")
            try:
                info = ydl.extract_info(f"ytsearch{results_per_query}:{q}", download=False)
            except Exception as ex:
                eprint(f"  search failed: {ex}")
                continue

            if not info:
                continue

            for entry in info.get("entries") or []:
                if not entry:
                    continue
                vid = entry.get("id")
                if not vid:
                    continue

                c = found.get(vid)
                if c is None:
                    c = Candidate(
                        video_id=vid,
                        title=entry.get("title") or "",
                        url=f"https://www.youtube.com/watch?v={vid}",
                        channel=entry.get("channel") or entry.get("uploader") or "",
                        duration=entry.get("duration"),
                    )
                    found[vid] = c
                if q not in c.search_queries:
                    c.search_queries.append(q)

    return found


def fetch_full_metadata(
    c: Candidate,
    cache_dir: Path,
    cookies_from_browser: Optional[str],
) -> bool:
    path = cache_dir / "metadata" / f"{c.video_id}.json"
    cached = cache_read_json(path)
    if cached is None:
        opts = base_ydl_opts(cookies_from_browser)
        opts.update({"skip_download": True})
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(c.url, download=False)
        except Exception as ex:
            eprint(f"[metadata skip] {c.video_id}: {ex}")
            return False
        if not info:
            return False

        cached = {
            "id": info.get("id"),
            "title": info.get("title"),
            "channel": info.get("channel") or info.get("uploader"),
            "upload_date": info.get("upload_date"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "webpage_url": info.get("webpage_url"),
        }
        cache_write_json(path, cached)

    c.title = cached.get("title") or c.title
    c.channel = cached.get("channel") or c.channel
    c.upload_date = cached.get("upload_date") or ""
    c.duration = cached.get("duration") if cached.get("duration") is not None else c.duration
    c.view_count = cached.get("view_count")
    c.url = cached.get("webpage_url") or c.url
    compute_metadata_score(c)
    return True


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

def parse_timestamp(ts: str) -> float:
    parts = ts.replace(",", ".").strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return 0.0


def parse_vtt(path: Path) -> list[CaptionLine]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[CaptionLine] = []
    current_start = 0.0
    last_norm = ""

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s == "WEBVTT" or s.startswith("Kind:") or s.startswith("Language:"):
            continue
        if "-->" in s:
            current_start = parse_timestamp(s.split("-->", 1)[0].strip())
            continue
        if s.isdigit():
            continue

        clean = re.sub(r"<[^>]+>", "", s)
        clean = html.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        norm = normalize_text(clean)

        if not norm or norm == last_norm:
            continue

        # Ignore pure positioning/settings noise.
        if re.fullmatch(r"(?:align|position|line|size|vertical)\S*", norm):
            continue

        out.append(CaptionLine(current_start, clean))
        last_norm = norm

    return out


def caption_windows(
    lines: list[CaptionLine],
    max_lines: int = 12,
    min_words: int = 12,
    max_words: int = 95,
) -> Iterable[tuple[float, str]]:
    n = len(lines)
    for i in range(n):
        parts: list[str] = []
        start = lines[i].start
        for j in range(i, min(n, i + max_lines)):
            parts.append(lines[j].text)
            text = " ".join(parts)
            wc = len(normalize_text(text).split())
            if wc >= min_words:
                yield start, text
            if wc >= max_words:
                break


def ordered_regex_score(text: str) -> tuple[float, str]:
    """
    Score ordered lore structure. Generic topical matches get much less credit.
    """
    t = normalize_text(text)
    best = (0.0, "")

    for name, components, base in STRICT_PATTERNS:
        pos = 0
        matched_spans = []
        ok = True

        for pattern in components:
            m = re.search(pattern, t[pos:])
            if not m:
                ok = False
                break
            abs_start = pos + m.start()
            abs_end = pos + m.end()
            matched_spans.append((abs_start, abs_end))
            pos = abs_end

        if not ok:
            continue

        spread_chars = matched_spans[-1][1] - matched_spans[0][0]
        spread_words = len(t[matched_spans[0][0]:matched_spans[-1][1]].split())

        # Tight phrasing is much more useful than the same words 2 minutes apart.
        if spread_words <= 28:
            tight_bonus = 3.0
        elif spread_words <= 45:
            tight_bonus = 2.0
        elif spread_words <= 65:
            tight_bonus = 1.0
        else:
            tight_bonus = 0.0

        score = base + tight_bonus
        if score > best[0]:
            best = (score, name)

    # Weak fallback evidence. Never let generic terms outrank ordered patterns.
    fallback = 0.0
    for term, weight in FALLBACK_TERMS:
        if term in t:
            fallback += weight
    fallback = min(fallback, 4.5)

    if fallback > best[0]:
        best = (fallback, "fallback-keywords")

    return best


def best_transcript_hit(lines: list[CaptionLine]) -> Optional[TranscriptHit]:
    hits: list[TranscriptHit] = []
    for ts, text in caption_windows(lines):
        score, pattern = ordered_regex_score(text)
        if score <= 0:
            continue
        hits.append(
            TranscriptHit(
                score=score,
                timestamp=ts,
                pattern=pattern,
                excerpt=re.sub(r"\s+", " ", text).strip(),
            )
        )

    if not hits:
        return None

    # Prefer structural matches, then earliest equal-scoring occurrence.
    hits.sort(key=lambda h: (-h.score, h.timestamp))
    return hits[0]


def download_captions(
    c: Candidate,
    cache_dir: Path,
    cookies_from_browser: Optional[str],
) -> tuple[list[Path], str]:
    sub_dir = cache_dir / "subs" / c.video_id
    sub_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(sub_dir.glob("*.vtt"))
    if existing:
        return existing, "cached"

    marker = sub_dir / "_NO_CAPTIONS"
    if marker.exists():
        return [], ""

    opts = base_ydl_opts(cookies_from_browser)
    opts.update({
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB", "en-orig"],
        "subtitlesformat": "vtt",
        "outtmpl": str(sub_dir / "%(id)s.%(ext)s"),
        "overwrites": True,
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # download() causes subtitle files to actually be written.
            rc = ydl.download([c.url])
            if rc not in (0, None):
                eprint(f"[captions] yt-dlp return code {rc} for {c.video_id}")
    except Exception as ex:
        eprint(f"[captions skip] {c.video_id}: {ex}")

    existing = sorted(sub_dir.glob("*.vtt"))
    if not existing:
        marker.write_text("No English captions downloaded.\n", encoding="utf-8")
    return existing, "downloaded"


def transcript_kind(path: Path) -> str:
    n = path.name.lower()
    if "orig" in n:
        return "en-orig"
    if "en-us" in n:
        return "en-US"
    if "en-gb" in n:
        return "en-GB"
    if ".en." in n or n.endswith(".en.vtt"):
        return "en"
    return path.suffix.lstrip(".")


def analyze_transcript(
    c: Candidate,
    cache_dir: Path,
    cookies_from_browser: Optional[str],
) -> bool:
    files, _ = download_captions(c, cache_dir, cookies_from_browser)
    best: Optional[TranscriptHit] = None
    best_kind = ""

    for p in files:
        try:
            lines = parse_vtt(p)
        except Exception as ex:
            eprint(f"[parse skip] {p.name}: {ex}")
            continue
        hit = best_transcript_hit(lines)
        if hit and (best is None or hit.score > best.score):
            best = hit
            best_kind = transcript_kind(p)

    if best is None:
        return False

    c.transcript_score = best.score
    c.transcript_timestamp = best.timestamp
    c.transcript_pattern = best.pattern
    c.transcript_excerpt = best.excerpt
    c.transcript_kind = best_kind
    return True


# ---------------------------------------------------------------------------
# Visual matching
# ---------------------------------------------------------------------------

def which_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def run_cmd(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def yt_dlp_cli_base(cookies_from_browser: Optional[str]) -> list[str]:
    cmd = [sys.executable, "-m", "yt_dlp"]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    return cmd


def download_short_clip(
    c: Candidate,
    center: float,
    clip_dir: Path,
    cookies_from_browser: Optional[str],
    radius: float,
) -> Optional[Path]:
    clip_dir.mkdir(parents=True, exist_ok=True)
    out = clip_dir / f"{c.video_id}_{int(center)}.mp4"
    if out.exists() and out.stat().st_size > 10_000:
        return out

    start = max(0.0, center - radius)
    end = center + radius

    # yt-dlp needs ffmpeg for --download-sections.
    cmd = yt_dlp_cli_base(cookies_from_browser) + [
        "--quiet",
        "--no-warnings",
        "--download-sections", f"*{start:.2f}-{end:.2f}",
        "--force-keyframes-at-cuts",
        "-f", "best[height<=480]/best",
        "--merge-output-format", "mp4",
        "-o", str(out),
        c.url,
    ]
    res = run_cmd(cmd, timeout=240)
    if res.returncode != 0 or not out.exists():
        eprint(f"[clip skip] {c.video_id}: {res.stderr[-500:]}")
        return None
    return out


def extract_frames(
    clip: Path,
    out_dir: Path,
    fps: float = 2.0,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("frame_*.jpg"))
    if existing:
        return existing

    pattern = str(out_dir / "frame_%05d.jpg")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-y", "-i", str(clip),
        "-vf", f"fps={fps}",
        "-q:v", "3",
        pattern,
    ]
    res = run_cmd(cmd, timeout=180)
    if res.returncode != 0:
        eprint(f"[frames skip] {clip.name}: {res.stderr[-500:]}")
        return []
    return sorted(out_dir.glob("frame_*.jpg"))


def crop_top_fraction(img: Image.Image, frac: float) -> Image.Image:
    frac = max(0.4, min(1.0, frac))
    w, h = img.size
    return img.crop((0, 0, w, max(1, int(h * frac))))


def dhash_bits(img: Image.Image, width: int = 16, height: int = 16) -> np.ndarray:
    gray = ImageOps.grayscale(img).resize((width + 1, height), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.int16)
    return (arr[:, 1:] > arr[:, :-1]).astype(np.uint8).ravel()


def ahash_bits(img: Image.Image, width: int = 16, height: int = 16) -> np.ndarray:
    gray = ImageOps.grayscale(img).resize((width, height), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.float32)
    return (arr > arr.mean()).astype(np.uint8).ravel()


def hash_similarity(a: Image.Image, b: Image.Image) -> float:
    da = dhash_bits(a)
    db = dhash_bits(b)
    aa = ahash_bits(a)
    ab = ahash_bits(b)
    dsim = 1.0 - float(np.mean(da != db))
    asim = 1.0 - float(np.mean(aa != ab))
    return 0.58 * dsim + 0.42 * asim


def cv_similarity(a: Image.Image, b: Image.Image) -> Optional[float]:
    if cv2 is None:
        return None

    a_rgb = np.asarray(a.convert("RGB"))
    b_rgb = np.asarray(b.convert("RGB"))
    ag = cv2.cvtColor(a_rgb, cv2.COLOR_RGB2GRAY)
    bg = cv2.cvtColor(b_rgb, cv2.COLOR_RGB2GRAY)

    # Normalize both to the same modest resolution.
    size = (384, 216)
    ag = cv2.resize(ag, size, interpolation=cv2.INTER_AREA)
    bg = cv2.resize(bg, size, interpolation=cv2.INTER_AREA)

    # Pixel correlation after normalization.
    agf = ag.astype(np.float32)
    bgf = bg.astype(np.float32)
    agf = (agf - agf.mean()) / (agf.std() + 1e-6)
    bgf = (bgf - bgf.mean()) / (bgf.std() + 1e-6)
    corr = float(np.mean(agf * bgf))
    corr01 = max(0.0, min(1.0, (corr + 1.0) / 2.0))

    # Edge overlap is useful for pixel-art/text screens.
    ea = cv2.Canny(ag, 60, 140) > 0
    eb = cv2.Canny(bg, 60, 140) > 0
    union = np.logical_or(ea, eb).sum()
    inter = np.logical_and(ea, eb).sum()
    edge_iou = float(inter / union) if union else 0.0

    return 0.74 * corr01 + 0.26 * edge_iou


def image_similarity(clue: Image.Image, frame: Image.Image, crop_frac: float) -> float:
    """
    Try a few plausible layout normalizations. Same-video frames should usually
    dominate even after YouTube re-encoding.
    """
    clue_c = crop_top_fraction(clue, crop_frac)

    variants: list[Image.Image] = []

    # Same full layout.
    variants.append(crop_top_fraction(frame, crop_frac))

    # Some uploads use small black borders. Trim a little from each side.
    w, h = frame.size
    for pct in (0.02, 0.04, 0.06):
        x = int(w * pct)
        y = int(h * pct)
        if 2 * x < w and 2 * y < h:
            trimmed = frame.crop((x, y, w - x, h - y))
            variants.append(crop_top_fraction(trimmed, crop_frac))

    best = 0.0
    for v in variants:
        hs = hash_similarity(clue_c, v)
        cs = cv_similarity(clue_c, v)
        if cs is None:
            s = hs
        else:
            s = 0.38 * hs + 0.62 * cs
        best = max(best, s)
    return best


def visual_match_candidate(
    c: Candidate,
    clue_path: Path,
    cache_dir: Path,
    output_dir: Path,
    cookies_from_browser: Optional[str],
    clip_radius: float,
    frame_fps: float,
    clue_crop_frac: float,
) -> bool:
    if c.transcript_timestamp is None:
        return False

    clip = download_short_clip(
        c,
        c.transcript_timestamp,
        cache_dir / "clips",
        cookies_from_browser,
        clip_radius,
    )
    if clip is None:
        return False

    frame_dir = cache_dir / "frames" / f"{c.video_id}_{int(c.transcript_timestamp)}"
    frames = extract_frames(clip, frame_dir, frame_fps)
    if not frames:
        return False

    clue = Image.open(clue_path).convert("RGB")

    scored: list[tuple[float, Path, float]] = []
    start = max(0.0, c.transcript_timestamp - clip_radius)

    for i, fp in enumerate(frames):
        try:
            frame = Image.open(fp).convert("RGB")
            s = image_similarity(clue, frame, clue_crop_frac)
        except Exception:
            continue

        # frame_00001 is approximately 1/fps seconds after clip start.
        local_t = (i + 1) / frame_fps
        absolute_t = start + local_t
        scored.append((s, fp, absolute_t))

    if not scored:
        return False

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_path, best_ts = scored[0]
    c.visual_score = best_score
    c.visual_timestamp = best_ts

    best_dir = output_dir / "best_frames"
    best_dir.mkdir(parents=True, exist_ok=True)
    copy_name = (
        f"{best_score:.4f}_{c.video_id}_{int(best_ts)}_"
        f"{safe_filename(c.title, 70)}.jpg"
    )
    dest = best_dir / copy_name
    shutil.copy2(best_path, dest)
    c.visual_frame = str(dest)

    # Save top 6 frame matches for this candidate as a contact sheet.
    make_contact_sheet(
        clue,
        scored[:6],
        output_dir / "contact_sheets" / f"{c.video_id}.jpg",
        c,
    )
    return True


def make_contact_sheet(
    clue: Image.Image,
    scored_frames: list[tuple[float, Path, float]],
    out_path: Path,
    c: Candidate,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    thumb_w, thumb_h = 360, 203
    pad = 14
    label_h = 34
    cols = 2
    rows = 1 + math.ceil(len(scored_frames) / cols)

    canvas = Image.new(
        "RGB",
        (cols * thumb_w + (cols + 1) * pad,
         rows * (thumb_h + label_h) + (rows + 1) * pad),
        "white",
    )
    draw = ImageDraw.Draw(canvas)

    # Clue first.
    clue_t = ImageOps.contain(clue, (thumb_w, thumb_h))
    canvas.paste(clue_t, (pad, pad))
    draw.text((pad, pad + thumb_h + 5), "CLUE", fill="black")

    x2 = pad * 2 + thumb_w
    info = f"{c.video_id}\n{c.channel}\n{fmt_date(c.upload_date)}"
    draw.multiline_text((x2, pad + 8), info[:130], fill="black", spacing=4)

    for idx, (score, fp, ts) in enumerate(scored_frames):
        r = 1 + idx // cols
        col = idx % cols
        x = pad + col * (thumb_w + pad)
        y = pad + r * (thumb_h + label_h)
        try:
            img = Image.open(fp).convert("RGB")
            img = ImageOps.contain(img, (thumb_w, thumb_h))
            canvas.paste(img, (x, y))
            draw.text((x, y + thumb_h + 5), f"{fmt_ts(ts)}  visual={score:.4f}", fill="black")
        except Exception:
            pass

    canvas.save(out_path, quality=90)


# ---------------------------------------------------------------------------
# Final scoring/reporting
# ---------------------------------------------------------------------------

def transcript_score01(raw: float) -> float:
    # Ordered patterns are 5..13ish; generic keyword hits <= 4.5.
    return max(0.0, min(1.0, raw / 12.0))


def compute_final_score(c: Candidate) -> None:
    t = transcript_score01(c.transcript_score)

    if c.visual_score is None:
        # Transcript-only ranking.
        c.final_score = 0.48 * c.metadata_score + 0.52 * t
    else:
        # Once visual evidence exists, it should dominate.
        c.final_score = (
            0.22 * c.metadata_score
            + 0.28 * t
            + 0.50 * c.visual_score
        )


def write_csv(candidates: list[Candidate], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "final_score", "metadata_score", "date_score", "title_score",
        "transcript_score", "visual_score",
        "video_id", "title", "channel", "upload_date", "duration",
        "nearest_anniversary", "anniversary_date", "anniversary_days",
        "transcript_pattern", "transcript_timestamp", "transcript_excerpt",
        "visual_timestamp", "visual_frame", "url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, c in enumerate(candidates, 1):
            w.writerow({
                "rank": i,
                "final_score": f"{c.final_score:.5f}",
                "metadata_score": f"{c.metadata_score:.5f}",
                "date_score": f"{c.date_score:.5f}",
                "title_score": f"{c.title_score:.5f}",
                "transcript_score": f"{c.transcript_score:.3f}",
                "visual_score": "" if c.visual_score is None else f"{c.visual_score:.5f}",
                "video_id": c.video_id,
                "title": c.title,
                "channel": c.channel,
                "upload_date": fmt_date(c.upload_date),
                "duration": fmt_ts(c.duration),
                "nearest_anniversary": c.nearest_anniversary,
                "anniversary_date": c.anniversary_date,
                "anniversary_days": c.anniversary_days,
                "transcript_pattern": c.transcript_pattern,
                "transcript_timestamp": fmt_ts(c.transcript_timestamp),
                "transcript_excerpt": c.transcript_excerpt,
                "visual_timestamp": fmt_ts(c.visual_timestamp),
                "visual_frame": c.visual_frame,
                "url": timestamp_url(c.url, c.transcript_timestamp),
            })


def write_json(candidates: list[Candidate], path: Path):
    data = []
    for rank, c in enumerate(candidates, 1):
        row = asdict(c)
        row["rank"] = rank
        row["upload_date_formatted"] = fmt_date(c.upload_date)
        row["duration_formatted"] = fmt_ts(c.duration)
        row["transcript_timestamp_formatted"] = fmt_ts(c.transcript_timestamp)
        row["visual_timestamp_formatted"] = fmt_ts(c.visual_timestamp)
        row["transcript_url"] = timestamp_url(c.url, c.transcript_timestamp)
        data.append(row)
    cache_write_json(path, data)


def html_escape(s) -> str:
    return html.escape("" if s is None else str(s))


def write_html(candidates: list[Candidate], path: Path):
    rows = []
    for i, c in enumerate(candidates, 1):
        frame_link = ""
        if c.visual_frame:
            try:
                rel = os.path.relpath(c.visual_frame, path.parent).replace("\\", "/")
                frame_link = f'<a href="{html_escape(rel)}">frame</a>'
            except Exception:
                frame_link = html_escape(c.visual_frame)

        rows.append(f"""
        <tr>
          <td>{i}</td>
          <td>{c.final_score:.3f}</td>
          <td>{c.metadata_score:.3f}</td>
          <td>{c.transcript_score:.1f}<br>{html_escape(c.transcript_pattern)}</td>
          <td>{"" if c.visual_score is None else f"{c.visual_score:.3f}"}</td>
          <td><a href="{html_escape(timestamp_url(c.url, c.transcript_timestamp))}">{html_escape(c.title)}</a><br>
              <small>{html_escape(c.channel)} · {html_escape(fmt_date(c.upload_date))}</small></td>
          <td>{html_escape(c.nearest_anniversary)}<br>
              <small>{html_escape(c.anniversary_days)} days</small></td>
          <td>{html_escape(fmt_ts(c.transcript_timestamp))}<br>
              <small>{html_escape(c.transcript_excerpt[:260])}</small></td>
          <td>{frame_link}</td>
        </tr>
        """)

    doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Zelda OSINT Hunter v2</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; background:#111; color:#eee; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border:1px solid #444; padding:8px; vertical-align:top; }}
th {{ position:sticky; top:0; background:#222; }}
a {{ color:#8ec5ff; }}
small {{ color:#bbb; }}
code {{ background:#222; padding:2px 4px; }}
</style>
</head>
<body>
<h1>Zelda OSINT Hunter v2</h1>
<p>Ranking uses anniversary proximity + retrospective-like title + ordered transcript evidence
+ visual similarity when available. The clue screenshot is <b>not</b> assumed to occur at 8:07.</p>
<table>
<thead>
<tr>
<th>#</th><th>Final</th><th>Meta</th><th>Transcript</th><th>Visual</th>
<th>Video</th><th>Anniversary</th><th>Transcript hit</th><th>Frame</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>"""
    path.write_text(doc, encoding="utf-8")


def print_top(candidates: list[Candidate], n: int = 25):
    print()
    print("=" * 110)
    print("TOP CANDIDATES")
    print("=" * 110)

    for i, c in enumerate(candidates[:n], 1):
        vis = "n/a" if c.visual_score is None else f"{c.visual_score:.3f}"
        print(
            f"\n#{i} FINAL={c.final_score:.3f} "
            f"META={c.metadata_score:.3f} "
            f"TRANSCRIPT={c.transcript_score:.1f} "
            f"VISUAL={vis}"
        )
        print(f"Title:   {c.title}")
        print(f"Channel: {c.channel}")
        print(f"Date:    {fmt_date(c.upload_date)}")
        print(
            f"Nearest: {c.nearest_anniversary} "
            f"({c.anniversary_days} days from {c.anniversary_date})"
        )
        print(f"Length:  {fmt_ts(c.duration)}")
        print(
            f"Hit:     {fmt_ts(c.transcript_timestamp)} "
            f"[{c.transcript_pattern}]"
        )
        print(f"URL:     {timestamp_url(c.url, c.transcript_timestamp)}")
        if c.visual_timestamp is not None:
            print(f"Frame:   {fmt_ts(c.visual_timestamp)}  {c.visual_frame}")
        print(f"Excerpt: {c.transcript_excerpt[:450]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Anniversary-first + ordered-transcript + visual-match YouTube OSINT hunter.",
    )
    ap.add_argument("--clue", type=Path, default=Path("clue.png"),
                    help="Challenge screenshot image.")
    ap.add_argument("--query", action="append", dest="queries",
                    help="Override/add a YouTube search query. Repeatable.")
    ap.add_argument("--results-per-query", type=int, default=35,
                    help="YouTube search results per query.")
    ap.add_argument("--metadata-prefetch", type=int, default=220,
                    help="Maximum unique search results to fully inspect.")
    ap.add_argument("--transcript-candidates", type=int, default=90,
                    help="Top metadata-ranked candidates whose captions are checked.")
    ap.add_argument("--visual-candidates", type=int, default=18,
                    help="Top transcript-ranked candidates to frame-match.")
    ap.add_argument("--max-anniversary-days", type=int, default=540,
                    help="Discard known-date videos farther than this from all target anniversaries.")
    ap.add_argument("--min-transcript-score", type=float, default=3.5,
                    help="Minimum ordered/fallback transcript score before visual stage.")
    ap.add_argument("--clip-radius", type=float, default=14.0,
                    help="Seconds before/after transcript hit to download.")
    ap.add_argument("--frame-fps", type=float, default=2.0,
                    help="Frames per second extracted from each short clip.")
    ap.add_argument("--clue-crop-frac", type=float, default=0.80,
                    help="Keep this top fraction of clue/frame to suppress YouTube captions.")
    ap.add_argument("--cookies-from-browser",
                    choices=["chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi"],
                    help="Use browser cookies if YouTube blocks anonymous access.")
    ap.add_argument("--cache-dir", type=Path, default=Path("zelda_hunt_cache"))
    ap.add_argument("--output-dir", type=Path, default=Path("zelda_hunt_output"))
    ap.add_argument("--no-visual", action="store_true",
                    help="Skip short-video downloads and frame matching.")
    ap.add_argument("--top", type=int, default=30,
                    help="Number of ranked candidates to print.")
    args = ap.parse_args()

    if not args.no_visual and not args.clue.exists():
        eprint(f"ERROR: clue image not found: {args.clue}")
        eprint("Put clue.png beside the script or pass --clue PATH")
        raise SystemExit(2)

    if not args.no_visual and which_ffmpeg() is None:
        eprint("WARNING: ffmpeg is not on PATH; switching to transcript-only mode.")
        eprint("Install ffmpeg, then rerun to enable frame matching.")
        args.no_visual = True

    if cv2 is None and not args.no_visual:
        eprint("NOTE: opencv-python is not installed.")
        eprint("Visual matching will use image hashes only. For stronger matching:")
        eprint("  pip install -U opencv-python")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    queries = args.queries or DEFAULT_QUERIES

    eprint(f"[1/5] Searching {len(queries)} queries × {args.results_per_query} results...")
    candidates_map = collect_search_results(
        queries, args.results_per_query, args.cookies_from_browser
    )
    candidates = list(candidates_map.values())
    eprint(f"Unique search hits: {len(candidates)}")

    # Rough title ordering before expensive full metadata retrieval.
    candidates.sort(key=lambda c: score_title(c.title), reverse=True)
    candidates = candidates[: args.metadata_prefetch]

    eprint(f"[2/5] Fetching full metadata for up to {len(candidates)} candidates...")
    kept: list[Candidate] = []
    for i, c in enumerate(candidates, 1):
        eprint(f"[metadata {i}/{len(candidates)}] {c.title[:90]}")
        if not fetch_full_metadata(c, args.cache_dir, args.cookies_from_browser):
            continue

        # Impossible final timestamp.
        if c.duration is not None and c.duration < 487:
            continue

        # Hard anniversary window only when date is known.
        if c.anniversary_days is not None and c.anniversary_days > args.max_anniversary_days:
            continue

        kept.append(c)

    kept.sort(key=lambda c: c.metadata_score, reverse=True)
    eprint(f"After date/duration filtering: {len(kept)}")

    transcript_pool = kept[: args.transcript_candidates]
    eprint(f"[3/5] Checking captions for top {len(transcript_pool)} metadata candidates...")

    transcript_hits: list[Candidate] = []
    for i, c in enumerate(transcript_pool, 1):
        eprint(
            f"[captions {i}/{len(transcript_pool)}] "
            f"meta={c.metadata_score:.3f} {c.title[:85]}"
        )
        if analyze_transcript(c, args.cache_dir, args.cookies_from_browser):
            compute_final_score(c)
            if c.transcript_score >= args.min_transcript_score:
                transcript_hits.append(c)

    transcript_hits.sort(
        key=lambda c: (
            transcript_score01(c.transcript_score),
            c.metadata_score,
        ),
        reverse=True,
    )

    eprint(f"Transcript hits above threshold: {len(transcript_hits)}")

    if not args.no_visual:
        visual_pool = transcript_hits[: args.visual_candidates]
        eprint(f"[4/5] Visual matching top {len(visual_pool)} transcript candidates...")
        for i, c in enumerate(visual_pool, 1):
            eprint(
                f"[visual {i}/{len(visual_pool)}] "
                f"trans={c.transcript_score:.1f} "
                f"{c.title[:85]}"
            )
            visual_match_candidate(
                c,
                args.clue,
                args.cache_dir,
                args.output_dir,
                args.cookies_from_browser,
                args.clip_radius,
                args.frame_fps,
                args.clue_crop_frac,
            )
            compute_final_score(c)
    else:
        eprint("[4/5] Visual matching skipped.")

    # Include transcript hits first, then metadata-only candidates for transparency.
    # Do not let generic metadata-only items outrank actual transcript evidence.
    for c in transcript_hits:
        compute_final_score(c)

    ranked = sorted(transcript_hits, key=lambda c: c.final_score, reverse=True)

    eprint("[5/5] Writing reports...")
    write_csv(ranked, args.output_dir / "ranked_candidates.csv")
    write_json(ranked, args.output_dir / "ranked_candidates.json")
    write_html(ranked, args.output_dir / "report.html")

    print_top(ranked, args.top)

    print()
    print("Reports:")
    print(f"  CSV:  {args.output_dir / 'ranked_candidates.csv'}")
    print(f"  JSON: {args.output_dir / 'ranked_candidates.json'}")
    print(f"  HTML: {args.output_dir / 'report.html'}")
    if not args.no_visual:
        print(f"  Contact sheets: {args.output_dir / 'contact_sheets'}")
        print(f"  Best frames:    {args.output_dir / 'best_frames'}")

    print()
    print("Interpretation:")
    print("  * A transcript score >= 7 usually means an ordered backstory pattern matched.")
    print("  * A high visual score is useful only when combined with a strong transcript/date fit.")
    print("  * Do NOT use proximity to 8:07 as a discovery signal.")
    print("  * After identifying the exact video, manually inspect 8:07 and count full hearts.")


if __name__ == "__main__":
    main()
