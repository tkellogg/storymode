import traceback
from typing import Self
import os
from flask import Flask, render_template, render_template_string, request, jsonify, g, current_app, redirect, url_for
from anthropic import Anthropic
from dotenv import load_dotenv
from db import db
from datetime import datetime
import asyncio
import nest_asyncio

load_dotenv()
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

# Initialize clients
anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_db():
    if not hasattr(g, '_database'):
        g._database = db
    return g._database

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, '_database'):
        current_app.ensure_sync(g._database.close)()

@app.route("/")
async def home():
    # Get published stories with author info
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
        LIMIT 10
    ''')
    return render_template("home.html", stories=stories[0]["result"])

@app.route("/story-builder")
async def story_builder():
    return render_template("story_builder.html")

@app.route("/stories/<story_id>/edit")
async def edit_story(story_id):
    # Get story details and chapters
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
        return "Story not found", 404

    chapters = await db.query('''
        SELECT chapter_number, created_at
        FROM chapter
        WHERE story = type::thing('story', $story_id)
        ORDER BY chapter_number;
    ''', {
        'story_id': story_id
    })

    return render_template(
        "story_editor.html",
        story=story[0]["result"][0],
        chapters=chapters[0]["result"] if chapters[0]["result"] else []
    )

@app.route("/api/stories", methods=["POST"])
async def create_story():
    prompt = request.form.get("prompt", "").strip()
    total_chapters = int(request.form.get("total_chapters", 10))
    words_per_chapter = int(request.form.get("words_per_chapter", 1000))

    if not prompt:
        return "Prompt is required", 400

    try:
        now = datetime.utcnow().isoformat()

        # Create new story with prompt as initial title
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
            raise ValueError(result[0]["result"])
        
        # Strip the 'story:' prefix from the ID
        story_id = str(result[0]["result"][0]["id"]).split(':')[1]
        return redirect(url_for('edit_story', story_id=story_id))

    except Exception as e:
        print("Error creating story:", e)
        traceback.print_exc()
        return f"Error creating story: {str(e)}", 500

@app.route("/api/stories/<story_id>/chapters", methods=["POST"])
async def generate_chapter(story_id):
    chapter_number = int(request.form.get("chapter_number", 1))

    try:
        # Get story details
        story = await db.query('''
            SELECT prompt, num_chapters, words_per_chapter
            FROM type::thing('story', $story_id);
        ''', {
            'story_id': story_id
        })

        if not story or not story[0]["result"]:
            return "<div class='error'>Story not found</div>", 404

        story_data = story[0]["result"][0]
        prompt = story_data["prompt"]
        total_chapters = story_data["num_chapters"]
        words_per_chapter = story_data["words_per_chapter"]

        now = datetime.utcnow().isoformat()

        # Generate chapter content with Claude
        chapter_prompt = f"Chapter {chapter_number} of {total_chapters}"
        if chapter_number == 1:
            chapter_prompt += f"\n\nStory prompt: {prompt}"
        else:
            # Get previous chapter for context
            prev_chapter = await db.query('''
                SELECT content
                FROM chapter
                WHERE story = type::thing('story', $story_id) AND chapter_number = $prev_num
                LIMIT 1;
            ''', {
                'story_id': story_id,
                'prev_num': chapter_number - 1
            })
            if prev_chapter and prev_chapter[0]["result"]:
                chapter_prompt += f"\n\nPrevious chapter:\n{prev_chapter[0]['result'][0]['content']}"

        message = anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=words_per_chapter * 2,  # Give some buffer
            temperature=0.9,
            system=(
                "You are a creative storyteller. Write engaging, vivid stories based on user prompts. "
                "Write only the story content, no other text. "
                f"Each chapter should be approximately {words_per_chapter} words."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Write {chapter_prompt}"
                }
            ]
        )
        
        chapter_content = message.content[0].text

        # After first chapter is written, generate a proper title
        if chapter_number == 1:
            title_message = anthropic.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=50,
                temperature=0.7,
                system="You are a creative writer who creates engaging, concise titles.",
                messages=[
                    {
                        "role": "user",
                        "content": f"Create a short, engaging title (max 5 words) for this story:\n\nPrompt: {prompt}\n\nFirst chapter:\n{chapter_content}"
                    }
                ]
            )
            
            title = title_message.content[0].text.strip('" ')

            # Update the story title
            await db.query('''
                UPDATE type::thing('story', $story_id)
                SET title = $title;
            ''', {
                'title': title,
                'story_id': story_id
            })

        # Save chapter
        await db.query('''
            CREATE chapter SET
                story = type::thing('story', $story_id),
                chapter_number = $chapter_number,
                content = $content,
                created_at = $now,
                updated_at = $now;
        ''', {
            'story_id': story_id,
            'chapter_number': chapter_number,
            'content': chapter_content,
            'now': now
        })

        return chapter_content

    except Exception as e:
        print("Unhandled error in generate_chapter:", e)
        traceback.print_exc()
        return f"<div class='error'>Error generating chapter: {str(e)}</div>", 500

@app.route("/api/stories/<story_id>/chapters/<int:chapter_number>")
async def get_chapter(story_id, chapter_number):
    try:
        chapter = await db.query('''
            SELECT content
            FROM chapter
            WHERE story = type::thing('story', $story_id) AND chapter_number = $chapter_number
            LIMIT 1;
        ''', {
            'story_id': story_id,
            'chapter_number': chapter_number
        })

        if not chapter or not chapter[0]["result"]:
            return "<div class='error'>Chapter not found</div>", 404

        return chapter[0]["result"][0]["content"]

    except Exception as e:
        print("Error fetching chapter:", e)
        return f"<div class='error'>Error loading chapter: {str(e)}</div>", 500

@app.route("/api/stories/<story_id>/chapters-list")
async def get_chapters_list(story_id):
    # Get story details for num_chapters
    story = await db.query('''
        SELECT num_chapters
        FROM type::thing('story', $story_id);
    ''', {
        'story_id': story_id
    })

    if not story or not story[0]["result"]:
        return "Story not found", 404

    # Get chapters
    chapters = await db.query('''
        SELECT chapter_number, created_at
        FROM chapter
        WHERE story = type::thing('story', $story_id)
        ORDER BY chapter_number;
    ''', {
        'story_id': story_id
    })

    return render_template(
        "chapters_list.html",
        story_id=story_id,
        chapters=chapters[0]["result"] if chapters[0]["result"] else [],
        num_chapters=story[0]["result"][0]["num_chapters"]
    )

@app.route("/api/stories/<story_id>", methods=["DELETE"])
async def delete_story(story_id):
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

        return "", 204

    except Exception as e:
        print("Error deleting story:", e)
        return f"Error deleting story: {str(e)}", 500

@app.route("/api/stories/<story_id>/title", methods=["PUT"])
async def update_story_title(story_id):
    try:
        title = request.form.get("title", "").strip()
        if not title:
            return "Title is required", 400

        await db.query('''
            UPDATE type::thing('story', $story_id)
            SET title = $title;
        ''', {
            'story_id': story_id,
            'title': title
        })

        return render_template_string('''
            <div class="title-display" hx-target="this" hx-swap="outerHTML">
                <h1>{{ title }}</h1>
                <button class="edit-btn" onclick="this.closest('.title-display').querySelector('h1').click()">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18">
                        <path fill="none" d="M0 0h24v24H0z"/>
                        <path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                    </svg>
                </button>
            </div>
        ''', title=title)

    except Exception as e:
        print("Error updating story title:", e)
        return f"Error updating title: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True) 