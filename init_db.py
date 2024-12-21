from db import db
import asyncio

async def init_schema():
    try:
        await db.ensure_connection()
        await db.query('''
            -- Define story table
            DEFINE TABLE story SCHEMAFULL;
            DEFINE FIELD title ON story TYPE string;
            DEFINE FIELD prompt ON story TYPE string;
            DEFINE FIELD created_at ON story TYPE string;
            DEFINE FIELD updated_at ON story TYPE string;
            DEFINE FIELD author ON story TYPE int;
            DEFINE FIELD num_chapters ON story TYPE int;
            DEFINE FIELD words_per_chapter ON story TYPE int;

            -- Define chapter table
            DEFINE TABLE chapter SCHEMAFULL;
            DEFINE FIELD story ON chapter TYPE record<story>;
            DEFINE FIELD chapter_number ON chapter TYPE int;
            DEFINE FIELD content ON chapter TYPE string;
            DEFINE FIELD created_at ON chapter TYPE string;
            DEFINE FIELD updated_at ON chapter TYPE string;
            DEFINE INDEX chapter_story_idx ON chapter COLUMNS story, chapter_number UNIQUE;
        ''')
        print("Schema initialized successfully")
    except Exception as e:
        print(f"Error initializing schema: {e}")
        raise
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(init_schema()) 