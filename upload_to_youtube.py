"""
YouTube Upload Script - Updated for 2025

Uses refresh token from GitHub Secrets to upload videos.
"""

import os
import sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
import datetime

# Configure UTF-8 encoding for console output (fixes Russian text display)
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def get_authenticated_service():
    """Authenticate using refresh token from environment."""
    
    # Get credentials from GitHub Secrets
    client_id = os.getenv('YT_CLIENT_ID')
    client_secret = os.getenv('YT_CLIENT_SECRET')
    refresh_token = os.getenv('YT_REFRESH_TOKEN')
    
    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Missing credentials! Set these GitHub Secrets:\n"
            "  - YT_CLIENT_ID\n"
            "  - YT_CLIENT_SECRET\n"
            "  - YT_REFRESH_TOKEN"
        )
    
    # Create credentials from refresh token
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"]
    )
    
    # Refresh to get access token
    creds.refresh(Request())
    
    return build('youtube', 'v3', credentials=creds)

def upload_to_youtube(video_file, title, description, tags=None, category_id='22'):
    """Upload video to YouTube and return result."""
    if tags is None:
        tags = ['История', 'Древний мир', 'Женщины в истории', 'History', 'Ancient History']
    youtube = get_authenticated_service()
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False,
        }
    }
    
    media = MediaFileUpload(
        str(video_file),
        chunksize=-1,
        resumable=True,
        mimetype='video/mp4'
    )
    
    print(f"[youtube] Uploading: {title}")
    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[youtube] Progress: {int(status.progress() * 100)}%")
    
    print(f"[youtube] ✅ Uploaded! Video ID: {response['id']}")
    print(f"[youtube] URL: https://youtube.com/shorts/{response['id']}")
    
    # Upload thumbnail if available
    thumbnail_file = Path('output/thumbnail.jpg')
    if thumbnail_file.exists():
        try:
            import io
            from PIL import Image
            img = Image.open(thumbnail_file)
            # Compress to stay under YouTube's 2MB limit
            thumb_bytes = io.BytesIO()
            quality = 85
            img.save(thumb_bytes, format='JPEG', quality=quality)
            while thumb_bytes.tell() > 2097152 and quality > 10:
                quality -= 10
                thumb_bytes = io.BytesIO()
                img.save(thumb_bytes, format='JPEG', quality=quality)
            thumb_bytes.seek(0)
            print(f"[youtube] Uploading thumbnail ({thumb_bytes.tell() // 1024}KB, quality={quality})...")
            youtube.thumbnails().set(
                videoId=response['id'],
                media_body=MediaIoBaseUpload(thumb_bytes, mimetype='image/jpeg', resumable=False)
            ).execute()
            print("[youtube] ✅ Thumbnail uploaded")
        except Exception as e:
            print(f"[youtube] ⚠️ Thumbnail upload failed: {e}")
    
    return response

def main():
    """Upload the generated video to YouTube."""
    upload_yt = os.getenv("UPLOAD_YOUTUBE", "true").lower()
    if upload_yt in ("false", "0", "no"):
        print("[youtube] ⏸️ Skipping YouTube upload (UPLOAD_YOUTUBE=false). Facebook & other platforms will proceed.")
        return

    video_file = Path('output/final_video.mp4')
    
    if not video_file.exists():
        print("[youtube] ❌ No video found at output/final_video.mp4")
        return
    
    # Read topic for the main title
    topic_file = Path('output/topic.txt')
    topic = ""
    if topic_file.exists():
        topic = topic_file.read_text(encoding='utf-8').strip()
    
    # Read story for description
    story_file = Path('output/story.txt')
    story = ""
    if story_file.exists():
        story = story_file.read_text(encoding='utf-8').strip()
    
    # Create title from topic
    if topic:
        title = topic[:57] + "..." if len(topic) > 60 else topic
    elif story:
        sentences = [s.strip() for s in story.split('.') if s.strip()]
        title = (sentences[0][:57] + "...") if sentences and len(sentences[0]) > 60 else (sentences[0] if sentences else story[:60])
    else:
        title = "История древних женщин"
    
    if len(title) < 15:
        title = f"{title} | История Древнего Мира"
    
    # Create description from topic + first few story sentences
    if story:
        sentences = [s.strip() for s in story.split('.') if s.strip()]
        description_text = '. '.join(sentences[:3]) + '.' if len(sentences) >= 3 else story[:300]
        description = f"""{description_text}

#история #древниймир #женщинывистории #интересныефакты #history #древняяистория"""
    else:
        description = "#история #древниймир #женщинывистории #интересныефакты"
    
    tags = [
        'История', 'Древний мир', 'Женщины в истории',
        'Интересные факты', 'Древняя история', 'Исторические факты',
        'История женщин', 'Античность'
    ]
    
    # Upload
    try:
        upload_to_youtube(
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            category_id='22'
        )
    except Exception as e:
        print(f"[youtube] ❌ Upload failed: {e}")
        raise

if __name__ == '__main__':
    main()
