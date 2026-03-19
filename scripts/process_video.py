import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir probieren verschiedene Türen zur ARD-Datenbank aus
API_URLS = [
    'https://www.tagesschau.de/api2u/news/',
    'https://www.tagesschau.de/api2u/homepage/',
    'https://www.tagesschau.de/api2u/channels/'
]
CONTENT_DIR = 'content/summaries'

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    video_url = None
    video_title = None
    video_id = None
    
    print('Starte die große Suche in der ARD-Datenbank...')
    
    for url in API_URLS:
        try:
            print(f'Prüfe Quelle: {url}')
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            # Suche in verschiedenen Listen nach 20:00 Uhr
            items = data.get('news', []) + data.get('items', []) + data.get('channels', [])
            
            for item in items:
                title = item.get('title', '') or item.get('name', '')
                if ('20:00' in title or '20 Uhr' in title) and 'tagesschau' in title.lower():
                    video_info = item.get('video') or item
                    streams = video_info.get('streams', {})
                    if streams:
                        video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                        video_title = title
                        video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                        break
            if video_url: break
        except Exception as e:
            print(f'Quelle {url} nicht erreichbar: {e}')

    if not video_url:
        print('Leider konnte keine 20-Uhr-Sendung gefunden werden. Wir probieren es später wieder!')
        return

    print(f'Gefunden! Titel: {video_title}')
    
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Diese Sendung haben wir schon im Sack. Abbruch.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print(f'Lade Video... {video_url}')
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini Verarbeitung (Passwort/Key aus GitHub Secrets)
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if not gemini_api_key:
        print('Fehler: GEMINI_API_KEY fehlt.')
        sys.exit(1)

    print('Gemini KI verarbeitet das Video (ca. 1-2 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
        
        while gfile.state.name == 'PROCESSING':
            time.sleep(5)
            gfile = client.files.get(name=gfile.name)
        
        prompt = 'Fasse die Sendung detailliert zusammen mit Überschriften und visueller Beschreibung zu jedem Beitrag. Antworte in Markdown.'
        # Wichtig: Wir nutzen das 2.0-flash Modell
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        frontmatter = f'---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(frontmatter + response.text)
        print('Erfolgreich gespeichert!')

        # 5. E-Mail via Resend
        resend_api_key = os.environ.get('RESEND_API_KEY')
        email_to = os.environ.get('EMAIL_TO')
        if resend_api_key and email_to:
            resend.api_key = resend_api_key
            html_content = markdown.markdown(response.text)
            resend.Emails.send({
                'from': 'Tagesschau KI <onboarding@resend.dev>',
                'to': [email_to],
                'subject': f'Zusammenfassung: {video_title}',
                'html': f'<h2>{video_title}</h2>{html_content}'
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile.name)
        except: pass

if __name__ == '__main__':
    main()
