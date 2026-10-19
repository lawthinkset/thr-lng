"""
Facebook Video / Reels Direct Upload - STRICTLY 1 SINGLE META API CALL
Direct multipart upload to Meta Graph Video API endpoint.
Publishes directly to Facebook Page feed in exactly 1 HTTP request.
Zero chunking sessions, zero status polling loops, zero comment retries.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment
for env_candidate in [Path(".env"), Path("../.env"), Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env"]:
    if env_candidate.exists():
        load_dotenv(dotenv_path=env_candidate, override=True)
        break
else:
    load_dotenv()


def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        print(msg.encode("ascii", "replace").decode("ascii"))


def upload_to_facebook(video_path, description, title="Video", thumbnail_path=None, page_id=None, access_token=None):
    """
    Uploads video to Facebook Page in EXACTLY ONE Meta Graph API call.
    Single direct multipart POST to https://graph-video.facebook.com/v21.0/{page_id}/videos
    """
    import requests

    access_token = access_token or os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
    page_id = page_id or os.getenv("FACEBOOK_PAGE_ID") or os.getenv("FB_PAGE_ID")

    if not access_token or not page_id:
        safe_print("[Facebook] Notice: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID not set. Skipping upload.")
        return None

    video_file = Path(video_path)
    if not video_file.exists():
        safe_print(f"[Facebook] Error: Video file not found: {video_path}")
        return None

    file_size_mb = video_file.stat().st_size / (1024 * 1024)

    safe_print("\n" + "=" * 60)
    safe_print("FACEBOOK VIDEO PUBLISH (STRICTLY 1 META API CALL)")
    safe_print("=" * 60)
    safe_print(f"[Facebook] Page ID: {page_id}")
    safe_print(f"[Facebook] Video: {video_file.name} ({file_size_mb:.2f} MB)")
    safe_print(f"[Facebook] Title: {str(title)[:70]}")
    safe_print(f"[Facebook] Description length: {len(str(description))} chars")

    upload_url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"

    data = {
        "title": str(title)[:100],
        "description": str(description)[:5000],
        "published": "true",
        "access_token": access_token
    }

    video_fp = None
    thumb_fp = None

    try:
        video_fp = open(video_file, "rb")
        files = {
            "source": (video_file.name, video_fp, "video/mp4")
        }

        # Attach thumbnail if available
        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                thumb_fp = open(thumbnail_path, "rb")
                files["thumb"] = (Path(thumbnail_path).name, thumb_fp, "image/jpeg")
            except Exception as te:
                safe_print(f"[Facebook] Notice reading thumbnail: {te}")

        safe_print("[Facebook] Sending single multipart POST request (API Call 1 of 1)...")
        res = requests.post(upload_url, data=data, files=files, timeout=600)

        if res.status_code in [200, 201]:
            res_data = res.json()
            video_id = res_data.get("id") or res_data.get("video_id")
            if video_id:
                safe_print("\n" + "=" * 60)
                safe_print("SUCCESS: FACEBOOK VIDEO PUBLISHED (EXACTLY 1 API CALL)!")
                safe_print(f"[Facebook] Video ID: {video_id}")
                safe_print(f"[Facebook] Video URL: https://www.facebook.com/{video_id}")
                safe_print("=" * 60)
                return {
                    "id": str(video_id),
                    "video_id": str(video_id),
                    "platform": "facebook",
                    "status": "success",
                    "url": f"https://www.facebook.com/{video_id}",
                    "published_at": datetime.now().isoformat(),
                    "api_calls_made": 1
                }

        safe_print(f"[Facebook] API Response ({res.status_code}): {res.text[:400]}")
        return None

    except requests.exceptions.Timeout:
        safe_print("[Facebook] Error: Upload request timed out.")
        return None
    except Exception as e:
        safe_print(f"[Facebook] Error during single-call upload: {e}")
        return None
    finally:
        if video_fp:
            try:
                video_fp.close()
            except Exception:
                pass
        if thumb_fp:
            try:
                thumb_fp.close()
            except Exception:
                pass


if __name__ == "__main__":
    test_file = Path("final_video.mp4")
    if test_file.exists():
        upload_to_facebook(str(test_file), "Daily automated post", "Daily Video")
