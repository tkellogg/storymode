from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

async def get_story(db, story_id: str) -> Optional[Dict[str, Any]]:
    """Get a single story's details."""
    try:
        story = await db.query('''
            SELECT 
                id,
                title,
                prompt,
                num_chapters,
                words_per_chapter
            FROM type::thing('story', $story_id)
        ''', {
            'story_id': story_id
        })

        if not story or not story[0]["result"]:
            return None

        return story[0]["result"][0]
    except Exception as e:
        print("Error fetching story:", e)
        return None

async def get_recent_stories(db, limit: int = 10) -> List[Dict[str, Any]]:
    """Get a list of recent stories."""
    try:
        stories = await db.query('''
            SELECT 
                id,
                title,
                prompt,
                created_at,
                num_chapters,
                words_per_chapter
            FROM story
            ORDER BY created_at DESC
            LIMIT $limit
        ''', {
            'limit': limit
        })
        return stories[0]["result"] if stories[0]["result"] else []
    except Exception as e:
        print("Error fetching recent stories:", e)
        return []

async def create_story(
    db,
    prompt: str,
    total_chapters: int = 10,
    words_per_chapter: int = 1000
) -> Tuple[Optional[str], Optional[str]]:
    """Create a new story and return its ID."""
    try:
        now = datetime.utcnow().isoformat()

        result = await db.query('''
            CREATE story SET
                title = $prompt,
                prompt = $prompt,
                author = 1,
                created_at = $now,
                updated_at = $now,
                num_chapters = $total_chapters,
                words_per_chapter = $words_per_chapter
            RETURN id;
        ''', {
            'prompt': prompt,
            'now': now,
            'total_chapters': total_chapters,
            'words_per_chapter': words_per_chapter
        })
        
        if result[0]["status"] == "ERR":
            return None, result[0]["result"]
        
        # Strip the 'story:' prefix from the ID
        story_id = str(result[0]["result"][0]["id"]).split(':')[1]
        return story_id, None

    except Exception as e:
        print("Error creating story:", e)
        return None, str(e)

async def delete_story(db, story_id: str) -> Tuple[bool, Optional[str]]:
    """Delete a story and all its chapters."""
    try:
        # Delete all chapters first
        await db.query('''
            DELETE chapter 
            WHERE story = type::thing('story', $story_id);
        ''', {
            'story_id': story_id
        })

        # Then delete the story
        await db.query('''
            DELETE type::thing('story', $story_id);
        ''', {
            'story_id': story_id
        })

        return True, None

    except Exception as e:
        print("Error deleting story:", e)
        return False, str(e)

async def get_story_chapters(db, story_id: str) -> List[Dict[str, Any]]:
    """Get all chapters for a story."""
    try:
        chapters = await db.query('''
            SELECT chapter_number, created_at
            FROM chapter
            WHERE story = type::thing('story', $story_id)
            ORDER BY chapter_number;
        ''', {
            'story_id': story_id
        })

        return chapters[0]["result"] if chapters[0]["result"] else []
    except Exception as e:
        print("Error fetching story chapters:", e)
        return [] 