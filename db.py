from typing import Self
from surrealdb import AsyncSurrealDB
import os
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self: Self) -> None:
        self.db = AsyncSurrealDB(url=os.getenv('SURREAL_URL'))


    async def close(self: Self) -> None:
        try:
            await self.db.close()
        except:
            print("Failed to close database connection")
            pass


    async def ensure_connection(self: Self) -> None:
        try:
            # Connect to SurrealDB
            await self.db.connect()
            await self.db.sign_in(username=os.getenv('SURREAL_USER'), password=os.getenv('SURREAL_PASS'))
            await self.db.use(os.getenv('SURREAL_NAMESPACE'), os.getenv('SURREAL_DATABASE'))

            # Define schema
            await self.db.query('''
                -- Define user table
                DEFINE TABLE user SCHEMAFULL;
                DEFINE FIELD email ON user TYPE string;
                DEFINE FIELD name ON user TYPE string;
                DEFINE FIELD created_at ON user TYPE datetime;
                DEFINE INDEX email_idx ON user COLUMNS email UNIQUE;

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

                -- Define draft table
                DEFINE TABLE draft SCHEMAFULL;
                DEFINE FIELD title ON draft TYPE string;
                DEFINE FIELD content ON draft TYPE string;
                DEFINE FIELD prompt ON draft TYPE string;
                DEFINE FIELD created_at ON draft TYPE datetime;
                DEFINE FIELD updated_at ON draft TYPE datetime;
                DEFINE FIELD author ON draft TYPE record<user>;
                DEFINE FIELD published_story ON draft TYPE record<story>;
            ''')
        except Exception as e:
            print(f"Database initialization error: {e}")
            raise


    async def query(self: Self, *args, **kwargs):
        await self.ensure_connection()
        return await self.db.query(*args, **kwargs)


# Create a singleton instance
db = Database() 