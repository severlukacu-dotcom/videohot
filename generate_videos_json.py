#!/usr/bin/env python3
"""
Quét thư mục chứa file .mp4 và tự sinh videos.json cho trang feed video ngắn.

Cách dùng:
    python3 generate_videos_json.py

Mặc định:
    - Đọc file .mp4 từ thư mục ./videos
    - Đọc thumbnail (nếu có) từ ./videos/thumbnails/<tên file>.jpg
    - Đọc override tiêu đề/caption/tác giả (nếu có) từ ./videos/meta.json
    - Ghi kết quả vào ./videos.json (ở gốc repo, cạnh index.html/reels.html)

Có thể tuỳ chỉnh qua biến môi trường:
    VIDEOS_DIR=videos OUTPUT=videos.json python3 generate_videos_json.py

Định dạng videos/meta.json (không bắt buộc), key là tên file:
{
  "my-clip.mp4": {
    "title": "Chuyến đi Đà Lạt",
    "caption": "Một ngày ở Đà Lạt 🌿",
    "author": "quocchienn",
    "likes": 12
  }
}

Lưu ý: script cố lấy thời lượng + độ phân giải video bằng ffprobe, và tự
tách 1 khung hình làm thumbnail bằng ffmpeg (nếu máy có cài ffmpeg và chưa
có sẵn thumbnail thủ công trong videos/thumbnails/). Nếu không có ffmpeg,
các trường đó để trống — trang web vẫn chạy bình thường, chỉ là không có
thời lượng/thumbnail tự động.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

VIDEOS_DIR = Path(os.environ.get("VIDEOS_DIR", "videos"))
OUTPUT = Path(os.environ.get("OUTPUT", "videos.json"))
THUMBS_DIR = VIDEOS_DIR / "thumbnails"
META_FILE = VIDEOS_DIR / "meta.json"


def prettify_title(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"[-_]+", " ", name).strip()
    return name[:1].upper() + name[1:] if name else filename


def format_size(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.1f} MB"


def ffprobe_info(path: Path):
    """Trả về (duration_seconds, width, height) nếu ffprobe có sẵn, ngược lại None."""
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        streams = data.get("streams", [{}])
        width = streams[0].get("width")
        height = streams[0].get("height")
        return duration, width, height
    except Exception:
        return None


def extract_thumbnail(video_path: Path, out_path: Path, duration_seconds: float) -> bool:
    """Tách 1 khung hình từ video làm thumbnail bằng ffmpeg. Trả về True nếu thành công."""
    if not shutil.which("ffmpeg"):
        return False
    # Lấy khung hình ở giây thứ 1, hoặc giữa video nếu video ngắn hơn 2s
    seek = 1.0 if (not duration_seconds or duration_seconds > 2) else duration_seconds / 2
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(seek), "-i", str(video_path),
                "-frames:v", "1", "-vf", "scale=640:-1",
                "-q:v", "3", str(out_path),
            ],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0 and out_path.exists()
    except Exception:
        return False


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def main():
    if not VIDEOS_DIR.exists():
        print(f"Không tìm thấy thư mục '{VIDEOS_DIR}'. Tạo thư mục này và đặt các file .mp4 vào trong.")
        return

    video_files = sorted(VIDEOS_DIR.glob("*.mp4"))
    if not video_files:
        print(f"Không có file .mp4 nào trong '{VIDEOS_DIR}'.")
        return

    meta_overrides = {}
    if META_FILE.exists():
        try:
            meta_overrides = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Cảnh báo] Không đọc được meta.json: {e}")

    THUMBS_DIR.mkdir(exist_ok=True)

    videos = []
    for video_path in video_files:
        override = meta_overrides.get(video_path.name, {})

        probe = ffprobe_info(video_path)
        duration_seconds = probe[0] if probe else 0
        duration = format_duration(duration_seconds) if probe else ""

        thumb_path = THUMBS_DIR / f"{video_path.stem}.jpg"
        thumb_status = "có sẵn"
        if not thumb_path.exists():
            if extract_thumbnail(video_path, thumb_path, duration_seconds):
                thumb_status = "tự tách bằng ffmpeg"
            else:
                thumb_status = "không tách được (thiếu ffmpeg?)"
        thumbnail = f"{THUMBS_DIR.as_posix()}/{thumb_path.name}" if thumb_path.exists() else ""

        entry = {
            "id": video_path.stem,
            "title": override.get("title") or prettify_title(video_path.name),
            "caption": override.get("caption", ""),
            "author": override.get("author", "quocchienn"),
            "likes": override.get("likes", 0),
            "duration": duration,
            "size": format_size(video_path.stat().st_size),
            "thumbnail": thumbnail,
            "url": f"{VIDEOS_DIR.as_posix()}/{video_path.name}",
        }
        videos.append(entry)
        print(f"[OK] {video_path.name} -> {entry['title']} | thumbnail: {thumb_status}" + (f" | {duration}" if duration else ""))

    OUTPUT.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nĐã ghi {len(videos)} video vào {OUTPUT}")


if __name__ == "__main__":
    main()
