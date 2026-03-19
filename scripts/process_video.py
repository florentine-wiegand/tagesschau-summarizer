import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys
import subprocess

# Wir nutzen yt-dlp direkt auf der Tagesschau-Webseite, das ist am sichersten!
SOURCE_URL = "https://www.tagesschau.de/multimedia/sendung/tagesschau/index.html"
CONTENT_DIR = "content/summaries"

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print("Suche die letzte 20-Uhr-Ausgabe auf tagesschau.de...")
    try:
        # Wir fragen yt-dlp, was das neueste Video auf der Übersichtsseite ist
        cmd = ["yt-dlp", "--dump-json", "--playlist-items", "1", SOURCE_URL]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Fehler beim Suchen: {result.stderr}")
            sys.exit(1)
            
        video_info = json.loads(result.stdout)
        video_url = video_info.get("webpage_url")
        video_title = video_info.get("title")
        video_id = video_info.get("id")
        
        print(f"Gefunden: {video_title} (ID: {video_id})")
        
        # Dateiname prüfen
        md_filename = os.path.join(CONTENT_DIR, f"{video_id}.md")
        if os.path.exists(md_filename):
            print("Diese Sendung haben wir schon zusammengefasst. Feierabend!")
            return

        # 2. Download in kleiner Qualität (geht schnell)
        video_file = "current_video.mp4"
        print("Lade Video herunter...")
        dl_cmd = ["yt-dlp", "-f", "worstvideo[ext=mp4]+worstaudio[ext=m4a]/mp4", "-o", video_file, video_url]
        subprocess.run(dl_cmd, check=True)
        
    except Exception as e:
        print(f"Fehler: {e}")
        sys.exit(1)

    # 3. Gemini KI Verarbeitung
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Fehler: Kein GEMINI_API_KEY gefunden.")
        sys.exit(1)

    print("Übermittele Video an Google Gemini KI (das dauert ca. 1 Min)...")
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
        
        while gfile.state.name == "PROCESSING":
            time.sleep(5)
            gfile = client.files.get(name=gfile.name)
        
        prompt = """
        Fasse die folgende Tagesschau-Sendung umfassend zusammen.
        Erstelle für jeden Beitrag eine Überschrift und eine detaillierte Zusammenfassung.
        Füge JEDEM Beitrag eine kurze 'VISUELLE BESCHREIBUNG' hinzu (was war im Video zu sehen?).
        Antworte in elegantem Markdown. Nutze Listen und Fettschrift.
        Schreibe ganz ans Ende ein Fazit zu den Kernthemen in 2 Sätzen.
        """
        
        print("KI schreibt Zusammenfassung...")
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        summary_text = response.text
        
        # 4. Speichern
        date_str = datetime.now().strftime("%Y-%m-%d")
        frontmatter = f"---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(frontmatter + summary_text)
        print(f"Artikel gespeichert!")

        # 5. E-Mail via Resend
        resend_api_key = os.environ.get("RESEND_API_KEY")
        email_to = os.environ.get("EMAIL_TO")
        if resend_api_key and email_to:
            print("Sende E-Mail Newsletter...")
            resend.api_key = resend_api_key
            html_content = markdown.markdown(summary_text)
            resend.Emails.send({
                "from": "Tagesschau KI <onboarding@resend.dev>",
                "to": [email_to],
                "subject": f"Zusammenfassung: {video_title}",
                "html": f"<h2>{video_title}</h2>{html_content}"
            })

    finally:
        if os.path.exists(video_file):
            os.remove(video_file)
        try: client.files.delete(name=gfile.name)
        except: pass

if __name__ == "__main__":
    main()
