import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir suchen jetzt SUPER-TIEF in der Datenbank
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
        print('Diese Sendung ist schon im Kasten.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print(f'Lade Video herunter...')
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini KI
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Gemini KI arbeitet jetzt (ca. 1-2 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        
        # Hochladen und sicherstellen, dass wir den Namen haben
        upload_resp = client.files.upload(path=video_file)
        # Wenn upload_resp ein Text ist, nimm ihn direkt, sonst nimm .name
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        
        # Warten, bis die Verarbeitung fertig ist
        gfile = client.files.get(name=gfile_name)
        while gfile.state.name == 'PROCESSING':
            print('KI analysiert noch...')
            time.sleep(10)
            gfile = client.files.get(name=gfile_name)
        
        prompt = 'Erstelle eine detaillierte Zusammenfassung der Nachrichtensendung in Markdown mit Überschriften und visueller Beschreibung zu jedem Beitrag.'
        response = client.models.generate_content(model='gemini-2.0-flash', contents=[gfile, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        # Metadaten bauen
        frontmatter = '---\ntitle: \"' + video_title + '\"\ndate: \"' + date_str + '\"\nvideoId: \"' + video_id + '\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(frontmatter + response.text)
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
                'subject': f'Zusammenfassung: {video_title}',
                'html': f'<h2>{video_title}</h2>{html_content}'
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile_name)
        except: pass

if __name__ == '__main__':
    main()
