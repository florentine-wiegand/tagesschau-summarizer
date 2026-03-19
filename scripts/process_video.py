import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Offizielle Tagesschau API für die 20 Uhr Sendung
API_URL = "https://www.tagesschau.de/api2u/news/"
CONTENT_DIR = "content/summaries"

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print("Suche aktuelle Tagesschau in der ARD-Datenbank...")
    try:
        req = urllib.request.Request(API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        video_url = None
        video_title = None
        video_id = None
        
        # Suche nach der 20 Uhr Sendung in den News
        for item in data.get('news', []):
            title = item.get('title', '')
            if 'tagesschau 20:00 Uhr' in title and item.get('type') == 'video':
                video_title = title
                # Nimm den MP4 Stream (meistens 'h264m' oder der erste verfügbare)
                streams = item.get('video', {}).get('streams', {})
                video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                video_id = item.get('externalId') or item.get('sophoraId')
                break
        
        if not video_url:
            print("Keine aktuelle 20-Uhr-Sendung in der API gefunden.")
            return

        print(f"Gefunden: {video_title}")
        print(f"Video-URL: {video_url}")
        
        # Dateiname basierend auf Video-ID
        md_filename = os.path.join(CONTENT_DIR, f"{video_id}.md")
        if os.path.exists(md_filename):
            print(f"Video bereits verarbeitet. Überspringe.")
            return

        # 2. Download
        video_file = "current_video.mp4"
        print("Lade Video direkt von ARD herunter...")
        urllib.request.urlretrieve(video_url, video_file)
        
    except Exception as e:
        print(f"Fehler beim Abrufen der Daten: {e}")
        sys.exit(1)

    # 3. Gemini KI Verarbeitung
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Fehler: Kein GEMINI_API_KEY gefunden.")
        sys.exit(1)

    print("Übermittele Video an Google Gemini KI...")
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
        
        while gfile.state.name == "PROCESSING":
            time.sleep(5)
            gfile = client.files.get(name=gfile.name)
        
        if gfile.state.name == "FAILED":
            print("KI-Verarbeitung fehlgeschlagen.")
            sys.exit(1)

        prompt = """
        Fasse die folgende Tagesschau-Sendung umfassend zusammen.
        Erstelle für jeden wichtigen Beitrag eine Überschrift und eine detaillierte Zusammenfassung.
        Füge JEDEM Beitrag eine kurze 'VISUELLE BESCHREIBUNG' hinzu (was war im Video zu sehen?).
        Antworte in elegantem Markdown. Nutze Listen und Fettschrift.
        Schreibe ganz ans Ende ein Fazit in 2 Sätzen.
        """
        
        print("KI schreibt Zusammenfassung...")
        # WICHTIG: Hier nutzen wir das aktuelle Modell
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        summary_text = response.text
        
        # 4. Speichern
        date_str = datetime.now().strftime("%Y-%m-%d")
        frontmatter = f"---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(frontmatter + summary_text)
        print(f"Artikel gespeichert: {md_filename}")

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
        # Aufräumen
        if os.path.exists(video_file):
            os.remove(video_file)
        try: 
            client.files.delete(name=gfile.name)
        except: 
            pass

if __name__ == "__main__":
    main()
