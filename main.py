import os
import re
import datetime
import subprocess
import random
import base64
from pathlib import Path
from urllib.parse import quote
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---------------- CONFIG ----------------

# Pollinations AI API Configuration (PAID)
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")
TEXT_MODEL = "gemini-fast"  # Google Gemini 2.5 Flash Lite
IMAGE_MODEL = "flux"  # Flux (high quality, photorealistic)

NUM_IMAGES = 8  # 8 unique scenes (faster generation)
IMAGE_WIDTH = 1920  # Full HD width
IMAGE_HEIGHT = 1080 # Full HD height (16:9 landscape)

STORY_MAX_WORDS = 500

TOPICS_FILE = Path("topics.txt")

IMAGES_DIR = Path("images")
OUTPUT_DIR = Path("output")
AUDIO_DIR = Path("audio")

MUSIC_FILE = AUDIO_DIR / "music.mp3"

NARRATION_FILE = OUTPUT_DIR / "narration.mp3"
STORY_FILE = OUTPUT_DIR / "story.txt"
SCENES_FILE = OUTPUT_DIR / "scenes.txt"
SUBS_FILE = OUTPUT_DIR / "subtitles.ass"
ANIMATED_VIDEO = OUTPUT_DIR / "animated.mp4"
VIDEO_WITH_SUBS = OUTPUT_DIR / "video_with_subs.mp4"
FINAL_VIDEO = OUTPUT_DIR / "final_video.mp4"

WHISPER_MODEL_NAME = "small"

# ----------------------------------------

def ensure_dirs():
    IMAGES_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)
    # Clean old images
    for f in IMAGES_DIR.glob("*.jpg"):
        f.unlink()

USED_TOPICS_FILE = Path("used_topics.txt")

def choose_topic_for_today():
    """Reads topics, checks used_topics.txt to find a NEW topic without burning it prematurely."""
    if not TOPICS_FILE.exists():
        raise ValueError("topics.txt file not found!")
        
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        topics = [line.strip() for line in f if line.strip()]
    
    if not topics:
        raise ValueError("No topics found in topics.txt!")
        
    used_topics = set()
    if USED_TOPICS_FILE.exists():
        try:
            with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
                used_topics = {line.strip() for line in f if line.strip()}
        except Exception as e:
            print(f"[topic] Warning reading used_topics.txt: {e}")
            
    # Find first topic not yet used
    today_topic = None
    for t in topics:
        if t not in used_topics:
            today_topic = t
            break
            
    # Fallback if all topics in file were already used
    if not today_topic:
        today_topic = topics[0]
            
    print(f"[topic] Selected topic: {today_topic}")
    return today_topic

def mark_topic_as_used(topic: str):
    """Mark topic as used and remove from topics.txt ONLY when video is completed."""
    if not TOPICS_FILE.exists():
        return
        
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        topics = [line.strip() for line in f if line.strip()]
        
    remaining_topics = [t for t in topics if t != topic]
    
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(topic + "\n")
        
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for t in remaining_topics:
            f.write(t + "\n")
            
    print(f"[topic] Saved: Marked topic as used: {topic}")

def generate_story_with_pollinations(topic: str) -> str:
    """Generate a short Russian story about ancient women's history using PAID API with model fallback."""
    
    if not POLLINATIONS_API_KEY:
        raise ValueError("POLLINATIONS_API_KEY not set! Get your API key from https://enter.pollinations.ai")
    
    url = "https://gen.pollinations.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Ты историк, специализирующийся на истории женщин в древних цивилизациях. "
        "Напиши подробный интересный рассказ на 2-3 минуты (350-500 слов) на русском языке. "
        "Расскажи о реальных исторических фактах, законах, обычаях или традициях. "
        "Используй живой, увлекательный стиль с деталями и примерами. Без заголовков."
    )
    user_prompt = f"Тема: {topic}. Расскажи подробную интересную историю с историческими фактами."
    
    models = ["openai", "mistral", "qwen", "gemini-fast"]
    
    print(f"[story] Generating Russian story for topic: {topic}")
    
    for attempt, model in enumerate(models):
        try:
            print(f"[story] Attempt {attempt+1}/{len(models)} using model '{model}'...")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 600
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            
            response_data = r.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                text = response_data["choices"][0]["message"]["content"].strip()
                if text and len(text) > 50:
                    words = text.split()
                    if len(words) > STORY_MAX_WORDS:
                        text = " ".join(words[:STORY_MAX_WORDS])
                    with open(STORY_FILE, "w", encoding="utf-8") as f:
                        f.write(text)
                    print(f"[story] ✅ Russian story generated with '{model}' ({len(text.split())} words)")
                    return text
        except Exception as e:
            print(f"[story] ⚠️ Model '{model}' failed: {e}")
            time.sleep(2)
            
    raise RuntimeError(f"Failed to generate story for topic '{topic}' with all models.")

def generate_scene_descriptions(story: str) -> list:
    """Extract distinct scene descriptions from the story sentences."""
    print(f"[scenes] Extracting {NUM_IMAGES} unique scene descriptions...")
    
    # Split story into sentences
    sentences = re.split(r'[.!?]+\s*', story.strip())
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
    
    # Create unique scenes from sentences
    scenes = []
    for i in range(NUM_IMAGES):
        if i < len(sentences):
            scene = sentences[i]
        else:
            # Cycle through sentences if we need more
            scene = sentences[i % len(sentences)]
        
        # Make each scene description more visual
        if i not in [j % len(sentences) for j in range(len(scenes))]:
            scenes.append(scene)
        else:
            # Add variation for repeated scenes
            variations = ["close-up view of", "wide shot of", "dramatic scene of", "peaceful moment of"]
            scenes.append(f"{variations[i % len(variations)]} {scene}")
    
    # Ensure uniqueness by adding index
    unique_scenes = []
    for i, scene in enumerate(scenes[:NUM_IMAGES]):
        unique_scenes.append(f"{scene}")
    
    # Save scenes
    with open(SCENES_FILE, "w", encoding="utf-8") as f:
        for i, scene in enumerate(unique_scenes):
            f.write(f"{i+1}. {scene}\n")
    
    print(f"[scenes] Created {len(unique_scenes)} unique scenes")
    return unique_scenes

def translate_to_english(russian_text: str) -> str:
    """Translate Russian text to English using Pollinations AI PAID API."""
    
    if not POLLINATIONS_API_KEY:
        print("[translate] Warning: No API key, using original text")
        return russian_text
    
    url = "https://gen.pollinations.ai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "user", "content": f"Translate this Russian text to English (only output the translation, nothing else): {russian_text}"}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }
    
    # Retry mechanism for translation
    for attempt in range(3):
        try:
            # Add Connection: close to prevent hangs
            headers["Connection"] = "close"
            
            if attempt == 0:
                print(f"[translate] Translating text...")
                
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            
            response_data = r.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                translation = response_data["choices"][0]["message"]["content"].strip()
                # Remove any quotes or extra text
                translation = translation.strip('"').strip("'").strip()
                print(f"[translate] ✅ Translation success")
                return translation
            else:
                raise ValueError("Invalid response format")
                
        except Exception as e:
            print(f"[translate] ⚠️ Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(1)
                continue
            print(f"[translate] ❌ Translation failed after 3 attempts, using original text.")
            return russian_text

def download_image_from_drive(idx: int) -> Path:
    """Download a random long-form image from Google Drive folder (weighted selection)."""
    import json
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    out = IMAGES_DIR / f"scene_{idx:02d}.jpg"
    
    service_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "11--jW208sZFcn64y3ADIOlihoz-S2Hri").strip().strip('"').strip("'")
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID environment variable required")
    
    cred = service_account.Credentials.from_service_account_info(
        json.loads(service_key), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=cred)
    
    all_files = []
    page_token = None
    while True:
        r = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            fields="files(id, name)", pageSize=200, pageToken=page_token
        ).execute()
        all_files.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token:
            break
    
    if not all_files:
        raise RuntimeError(f"No image files found in Google Drive folder: {folder_id}")
    
    used_log = Path("used_images.json")
    usage = {}
    if used_log.exists():
        try:
            usage = json.loads(used_log.read_text())
        except Exception:
            usage = {}
    
    for f in all_files:
        if f["name"] not in usage:
            usage[f["name"]] = 0
    
    min_usage = min(usage.values())
    weights = [1.0 / (usage[f["name"]] - min_usage + 1) for f in all_files]
    chosen = random.choices(all_files, weights=weights, k=1)[0]
    usage[chosen["name"]] += 1
    used_log.write_text(json.dumps(usage, indent=2))
    
    print(f"[image] Downloading {chosen['name']} from Drive...", flush=True)
    request = service.files().get_media(fileId=chosen["id"])
    from googleapiclient.http import MediaIoBaseDownload
    import io
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    out.write_bytes(fh.read())
    print(f"  Saved: {out.name} ({out.stat().st_size // 1024} KB)", flush=True)
    return out

def generate_image(scene: str, idx: int) -> Path:
    """Download image from Google Drive instead of AI generation."""
    return download_image_from_drive(idx)

def generate_images(scenes: list):
    """Download unique images for each scene from Google Drive."""
    print(f"[image] Downloading {NUM_IMAGES} long-form images from Google Drive...")
    return [generate_image(scene, i) for i, scene in enumerate(scenes)]


def sanitize_text_for_tts(text: str) -> str:
    """Clean and sanitize text before passing to TTS engines to avoid SSML and character errors."""
    if not text:
        return ""
    # Strip HTML and XML-like tags (e.g. <...> causes Microsoft SSML parse errors in edge-tts)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Strip markdown headers, bold, italics, code
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'[*_~`]', '', text)
    # Strip URLs
    text = re.sub(r'http\S+', '', text)
    # Normalize quotes, dashes
    text = text.replace('«', '"').replace('»', '"').replace('—', '-').replace('–', '-')
    # Keep Cyrillic, Latin letters, numbers, standard punctuation
    text = re.sub(r'[^\w\s.,!?:;\-\'"()]+', ' ', text, flags=re.UNICODE)
    # Normalize multiple whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def generate_tts(story: str):
    """
    Generate narration using a robust multi-tiered TTS pipeline:
    1. Edge-TTS (ru-RU-DmitryNeural / ru-RU-SvetlanaNeural) with multiple retries and backoff.
    2. OpenAI TTS (tts-1 with voice 'onyx') if OPENAI_API_KEY is available.
    3. gTTS (Google Translate TTS, 100% free, reliable) as ultimate fallback.
    """
    import asyncio
    clean_story = sanitize_text_for_tts(story)
    if not clean_story:
        clean_story = story.strip()

    print(f"[tts] Generating Russian narration ({len(clean_story.split())} words)...")

    def is_valid_audio(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 1024

    # Clean existing narration file if any
    if NARRATION_FILE.exists():
        try:
            NARRATION_FILE.unlink()
        except Exception:
            pass

    # ---------------- 1. EDGE-TTS (Primary) ----------------
    voices = ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"]
    for voice in voices:
        for attempt in range(1, 4):
            try:
                import edge_tts
                print(f"[tts] Trying edge-tts ({voice}, attempt {attempt}/3)...")

                async def _run_edge(v=voice):
                    communicate = edge_tts.Communicate(clean_story, v)
                    await communicate.save(str(NARRATION_FILE))

                asyncio.run(_run_edge())

                if is_valid_audio(NARRATION_FILE):
                    print(f"[tts] Narration generated with edge-tts ({voice}, {NARRATION_FILE.stat().st_size // 1024} KB)")
                    return
                else:
                    print(f"[tts] edge-tts returned an empty file (attempt {attempt}/3)")
            except Exception as e:
                print(f"[tts] edge-tts error ({voice}, attempt {attempt}/3): {e}")
                time.sleep(attempt * 2 + random.uniform(1, 3))

    print("[tts] edge-tts unavailable on this runner/IP. Falling back to secondary TTS...")

    # ---------------- 2. OPENAI TTS (High-Quality Fallback) ----------------
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and not openai_key.startswith("your_"):
        try:
            print("[tts] Trying OpenAI TTS (model: tts-1, voice: onyx)...")
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice="onyx",
                input=clean_story
            )
            with open(NARRATION_FILE, "wb") as f:
                f.write(response.content)

            if is_valid_audio(NARRATION_FILE):
                print(f"[tts] Narration generated with OpenAI TTS ({NARRATION_FILE.stat().st_size // 1024} KB)")
                return
        except Exception as e:
            print(f"[tts] OpenAI TTS failed: {e}")

    # ---------------- 3. gTTS (Guaranteed Free Fallback) ----------------
    try:
        print("[tts] Trying gTTS (Google Translate TTS) as guaranteed fallback...")
        from gtts import gTTS
        tts = gTTS(text=clean_story, lang="ru")
        tts.save(str(NARRATION_FILE))

        if is_valid_audio(NARRATION_FILE):
            print(f"[tts] Narration generated with gTTS ({NARRATION_FILE.stat().st_size // 1024} KB)")
            return
    except Exception as e:
        print(f"[tts] gTTS failed: {e}")

    raise RuntimeError("All TTS engines (edge-tts, OpenAI, gTTS) failed to generate narration audio!")

def generate_word_subtitles():
    """Generate one-line phrase subtitles at the bottom using Vosk."""
    print("[subs] Generating word-level Russian subtitles with Vosk...")
    
    import json
    import wave
    from vosk import Model, KaldiRecognizer
    import os
    
    # Download Vosk model if not exists
    model_path = "vosk-model-small-ru-0.22"
    if not os.path.exists(model_path):
        print("[subs] Downloading Vosk Russian model (~50 MB)...")
        import urllib.request
        import zipfile
        
        url = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
        zip_path = "vosk-model.zip"
        
        urllib.request.urlretrieve(url, zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        os.remove(zip_path)
        print("[subs] Model downloaded!")
    
    # Convert MP3 to WAV for Vosk
    wav_file = "output/narration.wav"
    os.system(f'ffmpeg -y -i {NARRATION_FILE} -ar 16000 -ac 1 {wav_file}')
    
    # Load Vosk model
    model = Model(model_path)
    
    # Open WAV file
    wf = wave.open(wav_file, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)  # Enable word-level timestamps
    
    # Process audio
    words = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            if 'result' in result:
                for word_info in result['result']:
                    words.append({
                        'word': word_info['word'].upper(),
                        'start': word_info['start'],
                        'end': word_info['end']
                    })
    
    # Final result
    final_result = json.loads(rec.FinalResult())
    if 'result' in final_result:
        for word_info in final_result['result']:
            words.append({
                'word': word_info['word'].upper(),
                'start': word_info['start'],
                'end': word_info['end']
            })
    
    # Group words into one-line subtitle phrases
    subtitle_lines = []
    current_group = []

    for word_info in words:
        should_break = False

        if current_group:
            # Break on significant pause (>0.5s silence between words)
            if word_info['start'] - current_group[-1]['end'] > 0.5:
                should_break = True
            # Break on sentence-ending punctuation
            elif current_group[-1]['word'] and current_group[-1]['word'][-1] in '.!?':
                should_break = True
            # Break if line has enough words (keep subtitles readable)
            elif len(current_group) >= 10:
                should_break = True

        if should_break:
            subtitle_lines.append({
                'text': ' '.join(w['word'] for w in current_group),
                'start': current_group[0]['start'],
                'end': current_group[-1]['end']
            })
            current_group = []

        current_group.append(word_info)

    if current_group:
        subtitle_lines.append({
            'text': ' '.join(w['word'] for w in current_group),
            'start': current_group[0]['start'],
            'end': current_group[-1]['end']
        })

    # Create ASS subtitle file
    ass_content = f"""[Script Info]
Title: Russian Story
ScriptType: v4.00+
PlayResX: {IMAGE_WIDTH}
PlayResY: {IMAGE_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,60,60,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    for line in subtitle_lines:
        start = line['start']
        end = line['end']
        text = line['text']
        
        start_time = f"{int(start//3600)}:{int((start%3600)//60):02d}:{start%60:.2f}"
        end_time = f"{int(end//3600)}:{int((end%3600)//60):02d}:{end%60:.2f}"
        
        ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
    
    # Save ASS file
    with open(SUBS_FILE, "w", encoding="utf-8") as f:
        f.write(ass_content)
    
    print(f"[subs] One-line subtitles saved ({len(subtitle_lines)} lines)")

def get_audio_duration(audio_file):
    """Get duration of audio file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def create_animated_slideshow(image_paths):
    """Create animated slideshow with Ken Burns zoom effect."""
    print("[video] Creating animated slideshow with Ken Burns effect...")
    
    # Get audio duration to match video length
    duration = get_audio_duration(NARRATION_FILE)
    per_image = duration / len(image_paths)
    
    # Create individual animated clips with zoom effect
    clips = []
    for i, img_path in enumerate(image_paths):
        clip_file = OUTPUT_DIR / f"clip_{i:02d}.mp4"
        clips.append(clip_file)
        
        # Calculate frames (30 fps)
        frames = max(int(per_image * 30), 60)
        
        # Alternate between zoom in and zoom out for variety
        if i % 2 == 0:
            # Zoom in effect
            zoom_start = 1.0
            zoom_end = 1.3
        else:
            # Zoom out effect  
            zoom_start = 1.3
            zoom_end = 1.0
        
        # Simple zoom with scale filter (more reliable on Windows)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-vf", (
                f"scale=8000:-1,"
                f"zoompan=z='if(lte(on,1),{zoom_start},{zoom_start}+(({zoom_end}-{zoom_start})/{frames})*on)':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={IMAGE_WIDTH}x{IMAGE_HEIGHT}:fps=30"
            ),
            "-t", str(per_image),
            "-c:v", "libx264",
            "-preset", "slow",  # Better quality
            "-crf", "18",  # High quality (lower = better, 18-23 is good)
            "-pix_fmt", "yuv420p",
            str(clip_file)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[video] Zoom failed for clip {i+1}, using fallback...")
            # Fallback: simple static with slight movement
            cmd_fallback = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(img_path),
                "-vf", f"scale={IMAGE_WIDTH}:{IMAGE_HEIGHT}:force_original_aspect_ratio=increase,crop={IMAGE_WIDTH}:{IMAGE_HEIGHT},fps=30",
                "-t", str(per_image),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(clip_file)
            ]
            subprocess.run(cmd_fallback, check=True, capture_output=True)
        
        print(f"[video] Animated clip {i+1}/{len(image_paths)}")
    
    # Create concat list
    concat_file = OUTPUT_DIR / "concat.txt"
    with open(concat_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip.resolve()}'\n")
    
    # Concatenate all clips
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(ANIMATED_VIDEO)
    ]
    subprocess.run(cmd, check=True)
    print(f"[video] Animated slideshow saved to {ANIMATED_VIDEO}")
    
    # Cleanup individual clips
    for clip in clips:
        if clip.exists():
            clip.unlink()

def add_subtitles():
    """Overlay ASS subtitles on video."""
    print("[video] Adding subtitles...")
    
    # Windows path needs special handling for FFmpeg filter
    subs_path = str(SUBS_FILE.resolve()).replace("\\", "/").replace(":", "\\:")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(ANIMATED_VIDEO),
        "-vf", f"ass='{subs_path}'",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(VIDEO_WITH_SUBS)
    ]
    subprocess.run(cmd, check=True)
    print(f"[video] Video with subtitles saved to {VIDEO_WITH_SUBS}")

def merge_audio():
    """Merge video with narration and background music."""
    print("[merge] Merging audio with background music...")
    
    if MUSIC_FILE.exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(VIDEO_WITH_SUBS),
            "-i", str(NARRATION_FILE),
            "-i", str(MUSIC_FILE),
            "-filter_complex",
            "[1:a]volume=1.0[a_voice];[2:a]volume=0.15[a_music];"
            "[a_voice][a_music]amix=inputs=2:duration=first:weights=1.0 0.2[a_out]",
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(FINAL_VIDEO)
        ]
    else:
        print("[merge] No music.mp3 found, using narration only")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(VIDEO_WITH_SUBS),
            "-i", str(NARRATION_FILE),
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            "-c:v", "copy",
            str(FINAL_VIDEO)
        ]
    
    subprocess.run(cmd, check=True)
    print(f"[merge] Final video saved to {FINAL_VIDEO}")

THUMBNAIL_FILE = OUTPUT_DIR / "thumbnail.jpg"

def generate_thumbnail(topic=""):
    """Choose one of the randomly downloaded images and set as YouTube thumbnail."""
    print("[thumbnail] Selecting one of the downloaded images as YouTube thumbnail...")
    import shutil
    image_files = list(IMAGES_DIR.glob("*.jpg"))
    if image_files:
        chosen_thumb = random.choice(image_files)
        shutil.copy2(chosen_thumb, THUMBNAIL_FILE)
        print(f"[thumbnail] ✅ Saved {chosen_thumb.name} as thumbnail to {THUMBNAIL_FILE}")
    else:
        print("[thumbnail] ⚠️ No downloaded images available for thumbnail")


def main():
    ensure_dirs()

    topic = choose_topic_for_today()
    print("=" * 60)
    print(f"=== Topic: {topic}")
    print("=" * 60)
    
    # Save topic for upload scripts to use as title
    topic_output_file = OUTPUT_DIR / "topic.txt"
    with open(topic_output_file, "w", encoding="utf-8") as f:
        f.write(topic)

    # 1. Generate story with Pollinations AI
    story = generate_story_with_pollinations(topic)
    
    # 2. Generate unique scene descriptions from the story
    scenes = generate_scene_descriptions(story)
    
    # 3. Generate unique images for each scene
    images = generate_images(scenes)

    # 4. Generate narration with TTS
    generate_tts(story)
    
    # 5. Generate word-level UPPERCASE subtitles with Whisper
    generate_word_subtitles()
    
    # 6. Create animated slideshow with Ken Burns effect
    create_animated_slideshow(images)
    
    # 7. Add subtitles overlay
    add_subtitles()
    
    # 8. Merge audio (narration + background music)
    merge_audio()

    # 9. Generate thumbnail
    generate_thumbnail(topic)

    # 10. Save video + description + thumbnail to timestamped folder
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)[:40]
    run_dir = OUTPUT_DIR / f"{timestamp}_{safe_topic}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Copy final video
    import shutil
    shutil.copy2(FINAL_VIDEO, run_dir / "final_video.mp4")

    # Copy thumbnail
    if THUMBNAIL_FILE.exists():
        shutil.copy2(THUMBNAIL_FILE, run_dir / "thumbnail.jpg")

    # Generate title & description file
    story_text = ""
    if STORY_FILE.exists():
        story_text = STORY_FILE.read_text(encoding="utf-8")

    desc_lines = [
        topic,
        "",
        story_text,
        "",
        "#история #древниймир #женщинывистории #интересныефакты #history"
    ]
    desc_text = "\n".join(desc_lines)

    title_desc_file = run_dir / "title_description.txt"
    title_desc_file.write_text(desc_text, encoding="utf-8")
    # Mark topic as completed only after successful video generation
    mark_topic_as_used(topic)

    print("=" * 60)
    print(f"✅ DONE. Video ready: {FINAL_VIDEO}")
    print(f"📁 Copy saved to: {run_dir}")
    print(f"📄 Title & description: {title_desc_file}")
    if THUMBNAIL_FILE.exists():
        print(f"🖼️  Thumbnail: {run_dir / 'thumbnail.jpg'}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Program stopped by user (KeyboardInterrupt).")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
