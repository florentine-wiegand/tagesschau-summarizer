import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir suchen tief in der Datenbank
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
    
    print('Suche im ARD-Archiv...')
    for url in API_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            items = data.get('news', []) + data.get('items', []) + data.get('results', [])
            
            for item in items:
                title = (item.get('title', '') or '').lower()
                if 'tagesschau' in title:
                    video_info = item.get('video') or item
                    streams = video_info.get('streams', {})
                    if streams:
                        video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                        video_title = item.get('title')
                        video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                        if '20:00' in title or '20 uhr' in title:
                            break
            if video_url: break
        except Exception as e:
            print(f'Fehler bei {url}: {e}')

    if not video_url:
        print('Keine Sendung gefunden.')
        return

    print(f'Verarbeite jetzt: {video_title}')
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Schon erledigt.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini KI
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('KI arbeitet (ca. 1-2 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        
        # Hochladen
        upload_resp = client.files.upload(path=video_file)
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        
        # WARTEN - Jetzt robust gegen Text/Objekt
        while True:
            file_info = client.files.get(name=gfile_name)
            # Wir machen den Status zu Text und wandeln ihn in GROSSBUCHSTABEN um
            status = str(file_info.state).upper()
            
            if 'ACTIVE' in status:
                break
            elif 'FAILED' in status:
                print('KI-Verarbeitung fehlgeschlagen.')
                sys.exit(1)
            else:
                print(f'KI analysiert noch (Status: {status})...')
                time.sleep(10)
        
        prompt = 'Erstelle eine detaillierte Zusammenfassung der Nachrichtensendung in Markdown mit Überschriften und visueller Beschreibung zu jedem Beitrag.'
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[file_info, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        # Metadaten bauen (manuelle Verkettung um Backslashes zu vermeiden)
        line1 = '---\ntitle: \"' + video_title + '\"\n'
        line2 = 'date: \"' + date_str + '\"\n'
        line3 = 'videoId: \"' + video_id + '\"\n---\n\n'
        
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(line1 + line2 + line3 + response.text)
        print('DATEI ERFOLGREICH GESPEICHERT!')

        # 5. E-Mail
        resend_api_key = os.environ.get('RESEND_API_KEY')
        email_to = os.environ.get('EMAIL_TO')
        if resend_api_key and email_to:
            resend.api_key = resend_api_key
            html_content = markdown.markdown(response.text)
            resend.Emails.send({
                'from': 'Tagesschau KI <onboarding@resend.dev>',
                'to': [email_to],
                'subject': f'KI-Zusammenfassung: {video_title}',
                'html': f'<h2>{video_title}</h2>{html_content}'
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile_name)
        except: pass

if __name__ == '__main__':
    main()
