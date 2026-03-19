import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir suchen jetzt SUPER-TIEF und mit Suchbegriff (20:00)
API_URLS = [
    'https://www.tagesschau.de/api2u/news/?pageSize=100&searchText=20:00',
    'https://www.tagesschau.de/api2u/news/?pageSize=100&searchText=tagesschau',
    'https://www.tagesschau.de/api2u/homepage/'
]
CONTENT_DIR = 'content/summaries'

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    video_url = None
    video_title = None
    video_id = None
    
    print('Suche tief im Archiv (100+ Meldungen)...')
    
    for url in API_URLS:
        try:
            print(f'Prüfe Quelle: {url}')
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            items = data.get('news', []) + data.get('items', []) + data.get('results', [])
            
            for item in items:
                title = (item.get('title', '') or '').lower()
                # 1. Priorität: 20 Uhr Sendung
                # 2. Priorität (Fallback): Irgendeine Tagesschau-Sendung von heute
                if 'tagesschau' in title:
                    video_info = item.get('video') or item
                    streams = video_info.get('streams', {})
                    if streams:
                        video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                        video_title = item.get('title')
                        video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                        
                        # Wenn es die 20 Uhr ist, nehmen wir sie sofort.
                        # Wenn es eine andere ist, speichern wir sie als Ersatz-Option.
                        if '20:00' in title or '20 uhr' in title:
                            print(f'Volltreffer: {video_title}')
                            break
                        else:
                            print(f'Ersatz-Option gefunden: {video_title}')
                            # Wir suchen trotzdem noch kurz weiter nach der 20:00er...
            
            if video_url: break
        except Exception as e:
            print(f'Fehler bei {url}: {e}')

    if not video_url:
        print('Unglaublich: Selbst im tiefen Archiv ist nichts zu finden. Wir warten auf 20 Uhr heute Abend!')
        return

    print(f'Verarbeite jetzt: {video_title}')
    
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Diese Sendung ist schon im Kasten.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print(f'Lade Video... {video_url}')
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Gemini arbeitet (1-2 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        gfile = client.files.upload(file=video_file)
        while gfile.state.name == 'PROCESSING':
            time.sleep(5)
            gfile = client.files.get(name=gfile.name)
        
        prompt = 'Fasse die Sendung detailliert in Markdown zusammen (mit Überschriften und was man im Bild sieht).'
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        frontmatter = f'---\ntitle: \"{video_title}\"\ndate: \"{date_str}\"\nvideoId: \"{video_id}\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(frontmatter + response.text)
        print('DATEI GESPEICHERT!')

        # 5. E-Mail
        resend_api_key = os.environ.get('RESEND_API_KEY')
        email_to = os.environ.get('EMAIL_TO')
        if resend_api_key and email_to:
            resend.api_key = resend_api_key
            resend.Emails.send({
                'from': 'Tagesschau KI <onboarding@resend.dev>',
                'to': [email_to],
                'subject': f'KI-Zusammenfassung: {video_title}',
                'html': markdown.markdown(response.text)
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile.name)
        except: pass

if __name__ == '__main__':
    main()
