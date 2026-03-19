import os
import json
import subprocess
import time
from datetime import datetime
from google import genai
import resend
import markdown

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL4A2F331EE86DCC22"
CONTENT_DIR = "content/summaries"

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    # 1. Fetch latest video from playlist (Tarnung als Android-Handy)
    print("Fetching playlist info...")
    cmd = [
        "yt-dlp", 
        "--extractor-args", "youtube:player_client=android", 
        "--dump-json", "--playlist-items", "1", PLAYLIST_URL
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error fetching playlist:", result.stderr)
        return
        
    try:
        video_info = json.loads(result.stdout)
    except Exception as e:
        print("Error parsing json video info:", e)
        return

    video_id = video_info.get("id")
    video_title = video_info.get("title")
    video_url = video_info.get("webpage_url")
    
    if not video_id:
        print("No video ID found.")
        return
        
    print(f"Latest video: {video_title} ({video_id})")
    
    # Check if we already processed it
    md_filename = os.path.join(CONTENT_DIR, f"{video_id}.md")
    if os.path.exists(md_filename):
        print(f"Video {video_id} already processed. Skipping.")
        return
        
    # 2. Download the video in low quality
    video_file = f"video_{video_id}.mp4"
    if not os.path.exists(video_file):
        print("Downloading video in low res...")
        dl_cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android",
            "-f", "worstvideo[ext=mp4]+worstaudio[ext=m4a]/mp4", 
            "-o", video_file, video_url
        ]
        subprocess.run(dl_cmd, check=True)
    
    # 3. Process with Gemini
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("No GEMINI_API_KEY found. Exiting.")
        return

    print("Uploading to Gemini...")
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
    except Exception as e:
        print("Error uploading to Gemini:", e)
        return
    
    print(f"File uploaded. Waiting for processing... State: {gfile.state.name}")
    while gfile.state.name == "PROCESSING":
        time.sleep(10)
        gfile = client.files.get(name=gfile.name)
        print(f"State: {gfile.state.name}")
        
    if gfile.state.name == "FAILED":
        print("Gemini processing failed.")
        return

    prompt = """
    Fasse die folgende Tagesschau-Sendung umfassend zusammen.
    Erstelle für jeden wichtigen Beitrag eine Überschrift und schreibe eine detaillierte Zusammenfassung.
    Füge außerdem JEDEM Beitrag eine kurze VISUELLE BESCHREIBUNG hinzu, was in dem Videobeitrag konkret zu sehen war (z.B. "Korrespondent steht vor einem Gebäude...").
    Antworte in elegantem, gut formatiertem Markdown. Nutze Listen und Hervorhebungen für gute Lesbarkeit.
    Schreibe ganz ans Ende ein Fazit zu den Kernthemen des Tages in maximal 2-3 Sätzen.
    """
    
    print("Generating summary...")
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[gfile, prompt]
    )
    
    summary_text = response.text
    
    # 4. Save Markdown file
    date_str = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n"
    
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(frontmatter + summary_text)
        
    print(f"Saved to {md_filename}")
    
    # 5. Send Email via Resend
    resend_api_key = os.environ.get("RESEND_API_KEY")
    email_to = os.environ.get("EMAIL_TO")
    
    if resend_api_key and email_to:
        print(f"Sending email to {email_to} via Resend...")
        resend.api_key = resend_api_key
        html_content = markdown.markdown(summary_text)
        try:
            r = resend.Emails.send({
                "from": "Tagesschau <onboarding@resend.dev>",
                "to": [email_to],
                "subject": f"Neu: {video_title}",
                "html": f"<h2>{video_title}</h2><br>{html_content}"
            })
            print("Email sent successfully!")
        except Exception as e:
            print("Failed to send email:", e)
    
    # Clean up
    if os.path.exists(video_file):
        os.remove(video_file)
        
    try:
        client.files.delete(name=gfile.name)
    except Exception as e:
        pass

if __name__ == "__main__":
    main()
