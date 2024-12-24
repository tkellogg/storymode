import asyncio
from typing import Optional, Tuple, List
import storage

async def migrate_chapter(db, story_id: str, chapter_number: int) -> bool:
    """Migrate a single chapter's content and audio to filesystem."""
    try:
        # Get chapter content from DB
        print("Getting chapter content from DB")
        chapter = await db.query('''
            SELECT content, Null as audio_data
            FROM chapter
            WHERE story = type::thing('story', $story_id)
            AND chapter_number = $chapter_number
            LIMIT 1;
        ''', {
            'story_id': story_id,
            'chapter_number': chapter_number
        })
        print("Chapter content:", chapter)

        if not chapter or not chapter[0]["result"]:
            print(f"No chapter found: {story_id} #{chapter_number}")
            return False

        result = chapter[0]["result"][0]
        success = True
        
        # Migrate text content
        if result.get('content'):
            try:
                # Save to file
                storage.save_chapter_text(story_id, chapter_number, result['content'])
                
                # Verify file was written correctly
                saved_text = storage.get_chapter_text(story_id, chapter_number)
                if not saved_text or saved_text != result['content']:
                    print(f"Failed to verify text for chapter {chapter_number}")
                    success = False
                else:
                    # Clear content from DB after successful file write
                    await db.query('''
                        UPDATE chapter 
                        SET content = NULL
                        WHERE story = type::thing('story', $story_id)
                        AND chapter_number = $chapter_number;
                    ''', {
                        'story_id': story_id,
                        'chapter_number': chapter_number
                    })
                    print(f"Migrated text for chapter {chapter_number}")
            except Exception as e:
                print(f"Error migrating text for chapter {chapter_number}:", e)
                success = False

        # Migrate audio data
        if result.get('audio_data'):
            try:
                # Save to file
                storage.save_chapter_audio(story_id, chapter_number, result['audio_data'])
                
                # Verify file was written correctly
                saved_audio = storage.get_chapter_audio(story_id, chapter_number)
                if not saved_audio or saved_audio != result['audio_data']:
                    print(f"Failed to verify audio for chapter {chapter_number}")
                    success = False
                else:
                    # Clear audio from DB after successful file write
                    await db.query('''
                        UPDATE chapter 
                        SET 
                            audio_data = NULL,
                            audio_mime = NULL
                        WHERE story = type::thing('story', $story_id)
                        AND chapter_number = $chapter_number;
                    ''', {
                        'story_id': story_id,
                        'chapter_number': chapter_number
                    })
                    print(f"Migrated audio for chapter {chapter_number}")
            except Exception as e:
                print(f"Error migrating audio for chapter {chapter_number}:", e)
                success = False

        return success

    except Exception as e:
        print(f"Error migrating chapter {chapter_number}:", e)
        raise

async def migrate_all_chapters(db) -> None:
    """Migrate all chapters to filesystem storage."""
    print("Starting storage migration...")
    
    # Get all chapters
    chapters = await db.query('''
        SELECT 
            story as story_id,
            chapter_number
        FROM chapter
        WHERE content is not NULL
        OR audio_data is not NULL;
    ''')

    if chapters and chapters[0]["status"] != "OK":
        raise ValueError("SurrealDB Error: " + chapters[0]["result"])

    if not chapters or not chapters[0]["result"]:
        print("No chapters to migrate")
        return

    # Track migration stats
    total = len(chapters[0]["result"])
    succeeded = 0
    failed = 0

    # Migrate each chapter
    for chapter in chapters[0]["result"]:
        story_id = chapter['story_id'].id
        if ':' in story_id:
            story_id = story_id.split(':')[1]
        chapter_number = chapter['chapter_number']
        print(f"Migrating chapter {chapter_number} of story {story_id}...")
        
        success = await migrate_chapter(db, story_id, chapter_number)
        if success:
            succeeded += 1
            print(f"Successfully migrated chapter {chapter_number}")
        else:
            failed += 1
            print(f"Failed to migrate chapter {chapter_number}")

    print(f"Storage migration complete. Succeeded: {succeeded}, Failed: {failed}, Total: {total}") 