import os
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv
import storage

load_dotenv()

# Initialize Anthropic client
anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

async def get_chapter(db, story_id, chapter_number):
    """Get a single chapter's content and audio status."""
    # Check if chapter exists in database
    chapter = await db.query('''
        SELECT 
            audio_mimetype ?? false as has_audio
        FROM chapter
        WHERE story = type::thing('story', $story_id) 
        AND chapter_number = type::int($chapter_number)
        LIMIT 1;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number
    })

    if not chapter or not chapter[0]["result"] or not chapter[0]["result"][0]:
        print(f"No chapter found for {story_id} #{chapter_number}")
        raise ValueError(f"Chapter not found: {story_id} #{chapter_number}")

    # Get content from filesystem
    content = storage.get_chapter_text(story_id, chapter_number)
    if not content:
        raise ValueError(f"Chapter content not found: {story_id} #{chapter_number}")

    result = chapter[0]["result"][0]
    result["content"] = content
    print(f"Chapter {chapter_number} data:", {
        'has_audio': result.get('has_audio'),
        'content_length': len(content),
    })
    # Ensure has_audio is a proper boolean
    result["has_audio"] = bool(result.get("has_audio", False))
    return result

async def get_chapters_list(db, story_id):
    """Get list of chapters for a story."""
    # Get story details for num_chapters
    story = await db.query('''
        SELECT num_chapters
        FROM type::thing('story', $story_id);
    ''', {
        'story_id': story_id
    })

    if not story or not story[0]["result"]:
        raise ValueError(f"Story not found: {story_id}")

    # Get chapters
    chapters = await db.query('''
        SELECT chapter_number, created_at
        FROM chapter
        WHERE story = type::thing('story', $story_id)
        ORDER BY chapter_number;
    ''', {
        'story_id': story_id
    })

    return (
        chapters[0]["result"] if chapters[0]["result"] else [],
        story[0]["result"][0]["num_chapters"]
    )

async def get_story_details(db, story_id):
    """Get story details needed for chapter generation."""
    story = await db.query('''
        SELECT prompt, num_chapters, words_per_chapter
        FROM type::thing('story', $story_id);
    ''', {
        'story_id': story_id
    })

    if not story or not story[0]["result"]:
        raise ValueError(f"Story not found: {story_id}")

    return story[0]["result"][0]

async def get_previous_chapter(db, story_id, chapter_number):
    """Get the content of the previous chapter."""
    if chapter_number <= 1:
        return None
        
    try:
        prev_chapter = await get_chapter(db, story_id, chapter_number - 1)
        return prev_chapter["content"] if prev_chapter else None
    except ValueError:
        return None

async def generate_chapter_content(story_data, chapter_number, prev_chapter_content=None):
    """Generate chapter content using Claude."""
    chapter_prompt = f"Chapter {chapter_number} of {story_data['num_chapters']}"
    
    if chapter_number == 1:
        chapter_prompt += f"\n\nStory prompt: {story_data['prompt']}"
    elif prev_chapter_content:
        chapter_prompt += f"\n\nPrevious chapter:\n{prev_chapter_content}"

    message = anthropic.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=story_data['words_per_chapter'] * 2,  # Give some buffer
        temperature=0.9,
        system=(
            "You are a creative storyteller. Write engaging, vivid stories based on user prompts. "
            "Write only the story content, no other text. "
            "Write in markdown format. Start the chapter with the chapter title in bold. "
            f"Each chapter should be approximately {story_data['words_per_chapter']} words."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Write {chapter_prompt}"
            }
        ]
    )
    
    return message.content[0].text

async def generate_title(prompt, first_chapter):
    """Generate a title for the story based on the first chapter."""
    title_message = anthropic.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=50,
        temperature=0.7,
        system="You are a creative writer who creates engaging, concise titles.",
        messages=[
            {
                "role": "user",
                "content": f"Create a short, engaging title (max 5 words) for this story:\n\nPrompt: {prompt}\n\nFirst chapter:\n{first_chapter}"
            }
        ]
    )
    
    return title_message.content[0].text.strip('" ')

async def save_chapter(db, story_id, chapter_number, content):
    """Save a new chapter to the database and filesystem."""
    now = datetime.utcnow().isoformat()
    
    # Save content to filesystem
    storage.save_chapter_text(story_id, chapter_number, content)
    
    # Create chapter record in database (with empty content to satisfy schema)
    result = await db.query('''
        CREATE chapter SET
            story = type::thing('story', $story_id),
            chapter_number = type::int($chapter_number),
            content = $content,
            created_at = $now,
            updated_at = $now
        RETURN AFTER;
    ''', {
        'story_id': story_id,
        'chapter_number': chapter_number,
        'content': '',  # Empty string to satisfy schema
        'now': now
    })

    if not result or result[0]["status"] == "ERR":
        raise ValueError("Failed to save chapter: " + str(result[0].get("result", "Unknown error")))
    print("Saved chapter to database", result[0])

    return result[0]["result"][0]

async def update_story_title(db, story_id, title):
    """Update the story's title."""
    result = await db.query('''
        UPDATE type::thing('story', $story_id)
        SET title = $title
        RETURN AFTER;
    ''', {
        'story_id': story_id,
        'title': title
    })

    if not result or not result[0]["result"]:
        raise ValueError("Failed to update title")

    return result[0]["result"][0]

async def generate_new_chapter(db, story_id, chapter_number):
    """Main function to generate and save a new chapter."""
    # Get story details
    story_data = await get_story_details(db, story_id)

    # Get previous chapter if needed
    prev_chapter = None
    if chapter_number > 1:
        prev_chapter = await get_previous_chapter(db, story_id, chapter_number)

    # Generate chapter content
    content = await generate_chapter_content(story_data, chapter_number, prev_chapter)

    # For first chapter, generate and update title
    if chapter_number == 1:
        title = await generate_title(story_data["prompt"], content)
        if title:
            await update_story_title(db, story_id, title)

    # Save the chapter
    await save_chapter(db, story_id, chapter_number, content)
    return content 