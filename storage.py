import os
from pathlib import Path
from typing import Optional

def get_user_data_dir() -> Path:
    """Get the user data directory, creating it if it doesn't exist."""
    data_dir = Path(os.getenv('USER_DATA_DIR'))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_chapter_dir(story_id: str, chapter_number: int) -> Path:
    """Get the directory for a specific chapter, creating it if it doesn't exist."""
    chapter_dir = get_user_data_dir() / 'story' / story_id / 'chapter' / str(chapter_number)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    return chapter_dir

def get_chapter_text_path(story_id: str, chapter_number: int) -> Path:
    """Get the path to the chapter's text file."""
    return get_chapter_dir(story_id, chapter_number) / 'text.md'

def get_chapter_audio_path(story_id: str, chapter_number: int) -> Path:
    """Get the path to the chapter's audio file."""
    return get_chapter_dir(story_id, chapter_number) / 'audio.mp3'

def save_chapter_text(story_id: str, chapter_number: int, content: str) -> None:
    """Save chapter text to file."""
    text_path = get_chapter_text_path(story_id, chapter_number)
    text_path.write_text(content, encoding='utf-8')

def save_chapter_audio(story_id: str, chapter_number: int, audio_data: bytes) -> None:
    """Save chapter audio to file."""
    audio_path = get_chapter_audio_path(story_id, chapter_number)
    audio_path.write_bytes(audio_data)

def get_chapter_text(story_id: str, chapter_number: int) -> Optional[str]:
    """Get chapter text from file."""
    text_path = get_chapter_text_path(story_id, chapter_number)
    if text_path.exists():
        return text_path.read_text(encoding='utf-8')
    return None

def get_chapter_audio(story_id: str, chapter_number: int) -> Optional[bytes]:
    """Get chapter audio from file."""
    audio_path = get_chapter_audio_path(story_id, chapter_number)
    if audio_path.exists():
        return audio_path.read_bytes()
    return None

def has_chapter_audio(story_id: str, chapter_number: int) -> bool:
    """Check if chapter has audio file."""
    return get_chapter_audio_path(story_id, chapter_number).exists() 