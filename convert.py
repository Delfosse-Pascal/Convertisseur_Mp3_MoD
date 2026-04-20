"""Convertisseur MP3/MOD - analyse + conversion + index.

Scan musiques/, convertit trackers (.mod/.xm/.it/.s3m) en MP3 via ffmpeg
(libopenmpt), génère miniatures waveform, JSON index, cache incrémental.

Dépendances: ffmpeg + ffprobe dans le PATH. Aucun pip requis.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "musiques"
IMG_DIR = ROOT / "images"
OUT_AUDIO = ROOT / "audio"
OUT_THUMBS = ROOT / "thumbs"
OUT_DATA = ROOT / "data"
HASH_CACHE = OUT_DATA / "hash_cache.json"
INDEX_JSON = OUT_DATA / "audio_index.json"
INDEX_JS = OUT_DATA / "audio_index.js"

TRACKER_EXTS = {".mod", ".xm", ".it", ".s3m"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
ALL_EXTS = TRACKER_EXTS | AUDIO_EXTS
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

FFMPEG_OPTS = ["-ar", "44100", "-ac", "2", "-b:a", "192k"]


def log(msg: str) -> None:
    print(msg, flush=True)


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            log(f"ERREUR: {tool} introuvable dans PATH.")
            log("Installer ffmpeg (build avec libopenmpt) et ré-essayer.")
            log("Windows: winget install ffmpeg  |  https://ffmpeg.org")
            sys.exit(1)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_cache() -> dict[str, Any]:
    if HASH_CACHE.exists():
        try:
            return json.loads(HASH_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    HASH_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def convert_to_mp3(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(src), *FFMPEG_OPTS, str(dst)])


def make_waveform(audio: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-i", str(audio),
        "-filter_complex",
        "showwavespic=s=480x120:colors=0x6cf6ff|0x3a9bff",
        "-frames:v", "1",
        str(dst),
    ])


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def fmt_duration(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "o" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} To"


def rel_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def scan_sources() -> list[Path]:
    if not SRC_DIR.exists():
        return []
    files = []
    for p in SRC_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALL_EXTS:
            files.append(p)
    return sorted(files)


def scan_banner_images() -> list[str]:
    if not IMG_DIR.exists():
        return []
    items = [
        rel_posix(p, ROOT)
        for p in sorted(IMG_DIR.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return items


def build_tree(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Nested dict tiroir -> sous-tiroir -> [tracks]."""
    tree: dict[str, Any] = {"folders": {}, "tracks": []}
    for entry in entries:
        rel_parts = Path(entry["source_rel"]).parts[:-1]
        node = tree
        for part in rel_parts:
            node = node["folders"].setdefault(part, {"folders": {}, "tracks": []})
        node["tracks"].append(entry)
    return tree


def cleanup_orphans(cache: dict[str, Any], active_keys: set[str]) -> None:
    stale = set(cache) - active_keys
    for key in stale:
        info = cache[key]
        for out_key in ("audio_out", "thumb_out"):
            out_rel = info.get(out_key)
            if out_rel:
                out_path = ROOT / out_rel
                if out_path.exists():
                    try:
                        out_path.unlink()
                        log(f"Supprimé: {out_rel}")
                    except OSError:
                        pass
        cache.pop(key, None)


def process_file(
    src: Path,
    cache: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    key = rel_posix(src, ROOT)
    size = src.stat().st_size
    mtime = int(src.stat().st_mtime)
    ext = src.suffix.lower()

    cached = cache.get(key)
    needs_rebuild = force or cached is None or cached.get("mtime") != mtime or cached.get("size") != size

    if not needs_rebuild:
        audio_out = ROOT / cached["audio_out"]
        thumb_out = ROOT / cached["thumb_out"]
        if audio_out.exists() and thumb_out.exists():
            return cached

    h = file_hash(src)
    audio_rel = f"audio/{src.relative_to(ROOT).with_suffix('.mp3').as_posix()}"
    thumb_rel = f"thumbs/{h}.png"
    audio_out = ROOT / audio_rel
    thumb_out = ROOT / thumb_rel

    if ext in TRACKER_EXTS:
        log(f"Conversion tracker → MP3: {key}")
        convert_to_mp3(src, audio_out)
    elif ext == ".mp3":
        audio_out.parent.mkdir(parents=True, exist_ok=True)
        if not audio_out.exists() or force:
            shutil.copy2(src, audio_out)
    else:
        log(f"Conversion audio → MP3: {key}")
        convert_to_mp3(src, audio_out)

    log(f"Waveform: {thumb_rel}")
    make_waveform(audio_out, thumb_out)
    duration = probe_duration(audio_out)

    entry = {
        "nom": src.stem,
        "source_rel": rel_posix(src, SRC_DIR),
        "original": src.name,
        "audio_out": audio_rel,
        "thumb_out": thumb_rel,
        "size": size,
        "size_fmt": fmt_size(size),
        "duration": duration,
        "duration_fmt": fmt_duration(duration),
        "hash": h,
        "mtime": mtime,
    }
    cache[key] = entry
    return entry


def main() -> None:
    check_tools()
    force = "--force" in sys.argv

    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_AUDIO.mkdir(parents=True, exist_ok=True)
    OUT_THUMBS.mkdir(parents=True, exist_ok=True)

    cache = load_cache()
    sources = scan_sources()
    log(f"{len(sources)} fichier(s) audio détecté(s).")

    entries = []
    active_keys: set[str] = set()
    for src in sources:
        try:
            entry = process_file(src, cache, force=force)
            entries.append(entry)
            active_keys.add(rel_posix(src, ROOT))
        except Exception as e:
            log(f"ERREUR sur {src.name}: {e}")

    cleanup_orphans(cache, active_keys)

    tree = build_tree(entries)
    banner = scan_banner_images()

    index = {
        "generated_at": int(Path(__file__).stat().st_mtime),
        "total": len(entries),
        "banner_images": banner,
        "tree": tree,
        "flat": entries,
    }

    INDEX_JSON.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    INDEX_JS.write_text(
        "window.AUDIO_INDEX = " + json.dumps(index, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    save_cache(cache)

    log(f"OK. Index: {INDEX_JSON.relative_to(ROOT)}  |  Tracks: {len(entries)}  |  Images bandeau: {len(banner)}")


if __name__ == "__main__":
    main()
