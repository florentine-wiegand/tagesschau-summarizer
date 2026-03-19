import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir schauen jetzt VIEL tiefer in die Datenbank (pageSize=50)
API_URLS = [
    'https://www.tagesschau.de/api2u/news/?pageSize=50',
    'https://www.tagesschau.de/api2u/homepage/',
    'https://www.tagesschau.de/api2u/channels/'
]
CONTENT_DIR = 'content/summaries'

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    video_url = None
    video_title = None
    video_id = None
    
    print('Starte die Hochleistungs-Suche im ARD-Archiv...')
    
    for url in API_URLS:
        try:
            print(f'Prüfe Quelle: {url}')
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            # Wir suchen in allen möglichen Listen, die die API liefert
            items = (data.get('news', []) + data.get('items', []) + 
                     data.get('channels', []) + data.get('subNews', []) +
                     data.get('results', []))
            
            for item in items:
                title = (item.get('title', '') or item.get('name', '') or '').lower()
                
                # Wir suchen flexibel nach (20:00 ODER 20.00 ODER 20 Uhr) UND tagesschau
                matches_time = ('20:00' in title or '20.00' in title or '20 uhr' in title)
                if matches_time and 'tagesschau' in title:
                    # Video-Infos rauskramen
                    video_info = item.get('video') or item
                    streams = video_info.get('streams', {})
                    if streams:
                        video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                        video_title = item.get('title') or item.get('name')
                        video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                        break
            if video_url: break
        except Exception as e:
            print(f'Quelle {url} nicht erreichbar: {e}')

    if not video_url:
        print('Die ARD hat die gestrige 20-Uhr-Sendung tief im Archiv vergraben. Wir probieren es später mit der frischen Sendung von heute!')
        return

    print(f'Gefunden! Titel: {video_title}')
    
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Diese Sendung ist schon verarbeitet. Wir warten auf die neue!')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print(f'Lade Video von ARD-Server... {video_url}')
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini Verarbeitung
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if not gemini_api_key:
        print('Fehler: GEMINI_API_KEY fehlt.')
        sys.exit(1)

    print('Gemini KI schreibt die Zusammenfassung (ca. 1 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
        
        while gfile.state.name == 'PROCESSING':
            time.sleep(5)
            gfile = client.files.get(name=gfile.name)
        
        prompt = 'Erstelle eine detaillierte Zusammenfassung der Nachrichtensendung in Markdown mit Überschriften und visueller Beschreibung der Bilder zu jedem Beitrag.'
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        frontmatter = f'---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(frontmatter + response.text)
        print('ERFOLG! Datei wurde in content/summaries gespeichert.')

        # 5. Email
        resend_api_key = os.environ.get('RESEND_API_KEY')
        email_to = os.environ.get('EMAIL_TO')
        if resend_api_key and email_to:
            resend.api_key = resend_api_key
            resend.Emails.send({
                'from': 'Tagesschau KI <onboarding@resend.dev>',
                'to': [email_to],
                'subject': f'Zusammenfassung: {video_title}',
                'html': markdown.markdown(response.text)
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile.name)
        except: pass

if __name__ == '__main__':
    main()
