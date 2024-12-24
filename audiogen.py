import os
from openai import OpenAI
from dotenv import load_dotenv
from io import BytesIO
from pydub import AudioSegment

load_dotenv()

# Initialize OpenAI client
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chunk_text(text: str, max_length: int = 4000) -> list[str]:
    """Split text into chunks that fit within OpenAI's TTS limit."""
    # Split on sentences to avoid cutting words
    sentences = text.replace('\n', ' ').split('. ')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        # Add period back except for last sentence
        sentence = sentence + '. ' if sentence != sentences[-1] else sentence
        if current_length + len(sentence) > max_length:
            if current_chunk:  # Save current chunk if it exists
                chunks.append(''.join(current_chunk))
            current_chunk = [sentence]
            current_length = len(sentence)
        else:
            current_chunk.append(sentence)
            current_length += len(sentence)
    
    if current_chunk:  # Add the last chunk
        chunks.append(''.join(current_chunk))
    
    return chunks

async def generate_audio(text: str) -> bytes:
    """Generate audio from text using OpenAI's TTS."""
    chunks = chunk_text(text)
    print(f"Split text into {len(chunks)} chunks")
    
    # Generate audio for each chunk
    audio_segments = []
    for i, chunk in enumerate(chunks, 1):
        print(f"Generating audio for chunk {i}/{len(chunks)} (length: {len(chunk)})")
        response = openai.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=chunk
        )
        # Convert bytes to AudioSegment
        audio_segment = AudioSegment.from_mp3(BytesIO(response.content))
        audio_segments.append(audio_segment)
    
    # Combine audio segments
    if len(audio_segments) == 1:
        # Convert single segment back to bytes
        buffer = BytesIO()
        audio_segments[0].export(buffer, format='mp3')
        return buffer.getvalue()
    
    # Concatenate all segments
    print(f"Concatenating {len(audio_segments)} audio segments")
    combined = audio_segments[0]
    for segment in audio_segments[1:]:
        combined = combined + segment
    
    # Export combined audio to bytes
    buffer = BytesIO()
    combined.export(buffer, format='mp3')
    return buffer.getvalue()

async def save_chapter_audio(db, story_id, chapter_number, audio_bytes):
    """Save audio data to the chapter in the database."""
    print(f"save_chapter_audio - chapter_number type: {type(chapter_number)}, value: {chapter_number}")
    # First verify the chapter exists
    chapter = await db.query('''
        SELECT id
        FROM chapter
        WHERE story = type::thing('story', $story_id) 
        AND chapter_number = type::int($chapter_number)
        LIMIT 1;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number
    })

    if not chapter or not chapter[0]["result"]:
        print(f"No chapter found to save audio: {story_id} #{chapter_number}")
        raise ValueError(f"Chapter not found: {story_id} #{chapter_number}")

    print(f"Saving audio data (length: {len(audio_bytes)} bytes)")

    # Save the audio using a parameterized query
    result = await db.query('''
        LET $chapter = (
            SELECT id 
            FROM chapter 
            WHERE story = type::thing('story', $story_id) 
            AND chapter_number = type::int($chapter_number)
            LIMIT 1
        );

        UPDATE $chapter[0]
        SET 
            audio_data = $audio_data,
            audio_mime = $audio_mime,
            updated_at = time::now()
        RETURN AFTER;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number,
        'audio_data': audio_bytes,
        'audio_mime': 'audio/mp3'
    })

    if not result or not result[0]["result"]:
        raise ValueError("Failed to save audio: no result from update query")

    updated = result[0]["result"][0]
    print(f"Audio saved. Updated record:", {
        'id': updated.get('id'),
        'has_audio': updated.get('audio_data') is not None,
        'audio_length': len(updated.get('audio_data', b'')) if updated.get('audio_data') else 0,
        'mime_type': updated.get('audio_mime')
    })

async def get_chapter_audio(db, story_id, chapter_number):
    """Retrieve audio data for a chapter from the database."""
    chapter = await db.query('''
        SELECT audio_data, audio_mime
        FROM chapter
        WHERE story = type::thing('story', $story_id) AND chapter_number = $chapter_number
        LIMIT 1;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number
    })

    if not chapter or not chapter[0]["result"] or not chapter[0]["result"][0]["audio_data"]:
        print(f"No audio found for story {story_id} chapter {chapter_number}", chapter[0]["result"])
        return None, None

    result = chapter[0]["result"][0]
    return result["audio_data"], result["audio_mime"]

async def get_chapter_text(db, story_id, chapter_number):
    """Get the text content of a chapter."""
    print(f"get_chapter_text - chapter_number type: {type(chapter_number)}, value: {chapter_number}")
    chapter = await db.query('''
        SELECT content
        FROM chapter
        WHERE story = type::thing('story', $story_id) AND chapter_number = type::int($chapter_number)
        LIMIT 1;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number
    })

    if not chapter or not chapter[0]["result"]:
        return None

    return chapter[0]["result"][0]["content"]
  