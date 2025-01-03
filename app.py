import traceback
from typing import Self
import os
from flask import Flask, render_template, render_template_string, request, jsonify, g, current_app, redirect, url_for, send_file
from dotenv import load_dotenv
from db import db
import asyncio
import nest_asyncio
import audiogen
import chapter
import story
import storage
import migrate_storage
from io import BytesIO
from pydub import AudioSegment
import tempfile

load_dotenv()
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

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
    stories = await story.get_recent_stories(db)
    return render_template("home.html", stories=stories)

@app.route("/story-builder")
async def story_builder():
    return render_template("story_builder.html")

@app.route("/stories/<story_id>/edit")
async def edit_story(story_id):
    story_data = await story.get_story(db, story_id)
    if not story_data:
        return "Story not found", 404

    chapters = await story.get_story_chapters(db, story_id)
    return render_template(
        "story_editor.html",
        story=story_data,
        chapters=chapters
    )

@app.route("/api/stories", methods=["POST"])
async def create_story_endpoint():
    prompt = request.form.get("prompt", "").strip()
    total_chapters = int(request.form.get("total_chapters", 10))
    words_per_chapter = int(request.form.get("words_per_chapter", 1000))

    if not prompt:
        return "Prompt is required", 400

    try:
        story_id, error = await story.create_story(
            db, 
            prompt=prompt,
            total_chapters=total_chapters,
            words_per_chapter=words_per_chapter
        )
        
        if error:
            return f"Error creating story: {error}", 500
            
        return redirect(url_for('edit_story', story_id=story_id))

    except Exception as e:
        print("Error in create_story_endpoint:", e)
        traceback.print_exc()
        return f"Error creating story: {str(e)}", 500

@app.route("/api/stories/<story_id>", methods=["DELETE"])
async def delete_story_endpoint(story_id):
    try:
        success, error = await story.delete_story(db, story_id)
        if not success:
            return f"Error deleting story: {error}", 500
        return "", 204

    except Exception as e:
        print("Error in delete_story_endpoint:", e)
        return f"Error deleting story: {str(e)}", 500

@app.route("/api/stories/<story_id>/chapters", methods=["POST"])
async def generate_chapter_endpoint(story_id):
    chapter_number = int(request.form.get("chapter_number", 1))

    try:
        content = await chapter.generate_new_chapter(db, story_id, chapter_number)
        return content

    except Exception as e:
        print("Error in generate_chapter_endpoint:", e)
        raise

@app.route("/api/stories/<story_id>/chapters/<int:chapter_number>/audio", methods=["POST"])
async def generate_chapter_audio_endpoint(story_id, chapter_number):
    # Get chapter content
    chapter_text = storage.get_chapter_text(story_id, chapter_number)
    if not chapter_text:
        return jsonify({"error": "Chapter not found"}), 404
    
    print(f"Generating audio for chapter {chapter_number} (text length: {len(chapter_text)})")
    
    # Generate audio
    audio_bytes = await audiogen.generate_audio(chapter_text)
    print(f"Generated audio length: {len(audio_bytes)} bytes")

    # Save to filesystem
    storage.save_chapter_audio(story_id, chapter_number, audio_bytes)
    print(f"Saved audio file for chapter {chapter_number}")
    
    # Return the audio player HTML
    return render_template_string('''
        <audio id="chapter-audio" controls>
            <source src="/api/stories/{{ story_id }}/chapters/{{ chapter_number }}/audio" type="audio/mp3">
            Your browser does not support the audio element.
        </audio>
    ''', story_id=story_id, chapter_number=chapter_number)

@app.route("/api/stories/<story_id>/chapters/<int:chapter_number>/audio")
async def get_chapter_audio_endpoint(story_id, chapter_number):
    audio_bytes = storage.get_chapter_audio(story_id, chapter_number)
    if not audio_bytes:
        return "No audio found", 404
    
    # Return as streaming audio
    return send_file(
        BytesIO(audio_bytes),
        mimetype='audio/mp3'
    )

@app.route("/api/stories/<story_id>/chapters-list")
async def get_chapters_list_endpoint(story_id):
    chapters, num_chapters = await chapter.get_chapters_list(db, story_id)
    if chapters is None:
        return "Story not found", 404

    # Check if audiobook exists
    has_audiobook = storage.has_audiobook(story_id)
    print(f"Checking audiobook for {story_id}: {has_audiobook}")

    return render_template(
        "chapters_list.html",
        story_id=story_id,
        chapters=chapters,
        num_chapters=num_chapters,
        has_audiobook=has_audiobook
    )

@app.route("/api/stories/<story_id>/title", methods=["PUT"])
async def update_story_title_endpoint(story_id):
    try:
        title = request.form.get("title", "").strip()
        if not title:
            return "Title is required", 400

        if not await chapter.update_story_title(db, story_id, title):
            return "Failed to update title", 500

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

@app.route("/api/stories/<story_id>/chapters/<int:chapter_number>")
async def get_chapter_endpoint(story_id, chapter_number):
    content = storage.get_chapter_text(story_id, chapter_number)
    if not content:
        raise ValueError(f"Chapter not found: {story_id} #{chapter_number}")

    has_audio = storage.has_chapter_audio(story_id, chapter_number)
    print(f"Rendering chapter {chapter_number} for story {story_id}; has_audio: {has_audio}")
    
    return render_template_string('''
        <div class="chapter-controls">
            {% if has_audio %}
                <audio id="chapter-audio" controls>
                    <source src="/api/stories/{{ story_id }}/chapters/{{ chapter_number }}/audio" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
            {% else %}
                <button id="generate-audio-btn" 
                        hx-post="/api/stories/{{ story_id }}/chapters/{{ chapter_number }}/audio"
                        hx-swap="outerHTML"
                        _="on htmx:beforeRequest 
                           add .hidden to <button#generate-audio-btn/>
                           remove .hidden from <div#audio-loading/>">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
                        <path fill="none" d="M0 0h24v24H0z"/>
                        <path fill="currentColor" d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                    </svg>
                    Generate Audio
                </button>
                <div id="audio-loading" class="loading hidden">
                    <div class="loading-spinner"></div>
                    <span>Generating audio...</span>
                </div>
            {% endif %}
        </div>
        <div class="chapter-content">{{ content | safe }}</div>
    ''', 
    content=content,
    has_audio=has_audio,
    story_id=story_id,
    chapter_number=chapter_number
    )

@app.route("/api/stories/<story_id>/generate-all", methods=["POST"])
async def generate_all_endpoint(story_id):
    try:
        # Get story details
        story_data = await story.get_story(db, story_id)
        if not story_data:
            return "Story not found", 404

        # Generate all remaining chapters
        chapters, num_chapters = await chapter.get_chapters_list(db, story_id)
        current_chapters = len(chapters)
        
        for chapter_num in range(current_chapters + 1, num_chapters + 1):
            print(f"Generating chapter {chapter_num}")
            content = await chapter.generate_new_chapter(db, story_id, chapter_num)
            
            # Generate audio for this chapter
            print(f"Generating audio for chapter {chapter_num}")
            audio_bytes = await audiogen.generate_audio(content)
            storage.save_chapter_audio(story_id, chapter_num, audio_bytes)
        
        # Generate audio for any existing chapters that don't have it
        for chapter_num in range(1, current_chapters + 1):
            if not storage.has_chapter_audio(story_id, chapter_num):
                print(f"Generating missing audio for chapter {chapter_num}")
                content = storage.get_chapter_text(story_id, chapter_num)
                audio_bytes = await audiogen.generate_audio(content)
                storage.save_chapter_audio(story_id, chapter_num, audio_bytes)
        
        # Return the last chapter's content
        content = storage.get_chapter_text(story_id, num_chapters)
        has_audio = storage.has_chapter_audio(story_id, num_chapters)
        
        return render_template_string('''
            <div class="chapter-controls">
                {% if has_audio %}
                    <audio id="chapter-audio" controls>
                        <source src="/api/stories/{{ story_id }}/chapters/{{ chapter_number }}/audio" type="audio/mp3">
                        Your browser does not support the audio element.
                    </audio>
                {% endif %}
            </div>
            <div class="chapter-content">{{ content | safe }}</div>
        ''', 
        content=content,
        has_audio=has_audio,
        story_id=story_id,
        chapter_number=num_chapters
        )

    except Exception as e:
        print("Error in generate_all_endpoint:", e)
        raise

@app.route("/api/stories/<story_id>/audiobook", methods=["POST"])
async def generate_audiobook_endpoint(story_id):
    try:
        # Get all chapters
        chapters, num_chapters = await chapter.get_chapters_list(db, story_id)
        if not chapters:
            return "No chapters found", 404

        # Check if all chapters have audio
        for chapter_num in range(1, num_chapters + 1):
            if not storage.has_chapter_audio(story_id, chapter_num):
                return "Not all chapters have audio generated", 400

        print(f"Generating audiobook for story {story_id}")
        
        # Concatenate all audio files
        combined = AudioSegment.empty()
        for chapter_num in range(1, num_chapters + 1):
            audio_bytes = storage.get_chapter_audio(story_id, chapter_num)
            print(f"Adding chapter {chapter_num} audio ({len(audio_bytes)} bytes)")
            
            # Save bytes to temp file because pydub needs a file
            with tempfile.NamedTemporaryFile(suffix='.mp3') as temp_file:
                temp_file.write(audio_bytes)
                temp_file.flush()
                
                # Load the audio and add it to combined
                audio_segment = AudioSegment.from_mp3(temp_file.name)
                if len(combined) > 0:
                    # Add 1 second of silence between chapters
                    combined += AudioSegment.silent(duration=1000)
                combined += audio_segment

        # Export combined audio to bytes
        with tempfile.NamedTemporaryFile(suffix='.mp3') as temp_file:
            combined.export(temp_file.name, format='mp3')
            temp_file.seek(0)
            final_audio_bytes = temp_file.read()

        print(f"Saving audiobook ({len(final_audio_bytes)} bytes)")
        # Save to disk
        storage.save_audiobook(story_id, final_audio_bytes)

        # Return audio player HTML
        return render_template_string('''
            <audio id="audiobook-player" controls>
                <source src="/api/stories/{{ story_id }}/audiobook" type="audio/mp3">
                Your browser does not support the audio element.
            </audio>
        ''', story_id=story_id)

    except Exception as e:
        print("Error creating audiobook:", e)
        traceback.print_exc()
        return f"Error creating audiobook: {str(e)}", 500

@app.route("/api/stories/<story_id>/audiobook", methods=["GET"])
async def get_audiobook_endpoint(story_id):
    try:
        audio_bytes = storage.get_audiobook(story_id)
        if not audio_bytes:
            return "Audiobook not found", 404

        # Return as streamable audio
        return send_file(
            BytesIO(audio_bytes),
            mimetype='audio/mp3'
        )

    except Exception as e:
        print("Error serving audiobook:", e)
        traceback.print_exc()
        return f"Error serving audiobook: {str(e)}", 500

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('images/favicon.png')

if __name__ == "__main__":
    app.run(debug=True) 