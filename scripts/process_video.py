import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir graben jetzt richtig tief nach der 20-Uhr-Sendung
API_URLS = [
    'https://www.tagesschau.de/api2u/news/?pageSize=100',
    'https://www.tagesschau.de/api2u/channels/',
    'https://www.tagesschau.de/api2u/homepage/'
]
CONTENT_DIR = 'content/summaries'

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    video_url = None
    video_title = None
    video_id = None
    
    current_year = str(datetime.now().year)
    print(f'Starte Tiefensuche im Archiv für {current_year}...')
    
    for url in API_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            items = data.get('news', []) + data.get('items', []) + data.get('results', []) + data.get('channels', [])
            
            for item in items:
                title = (item.get('title', '') or item.get('name', '') or '').lower()
                
                # Wir suchen nach der 20-Uhr-Sendung ODER einer langen Tagesschau-Folge (>10 Min)
                is_tagesschau = 'tagesschau' in title
                is_20uhr = ('20:00' in title or '20 uhr' in title) and '100 sekunden' not in title
                
                # Als Fallback nehmen wir alles, was nach Hauptsendung aussieht
                if is_tagesschau and (is_20uhr or current_year in title):
                    video_info = item.get('video') or item
                    streams = video_info.get('streams', {})
                    if streams:
                        video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                        video_title = item.get('title') or item.get('name')
                        video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                        # Wir nehmen sie sofort!
                        break
            if video_url: break
        except Exception:
            continue

    if not video_url:
        print('Die ARD hat die gestrige 20-Uhr-Sendung schon tief versteckt. Wir probieren es trotzdem!')
        return

    print(f'Gefunden! Verarbeite jetzt: {video_title}')
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Schon erledigt.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini 3.1 Flash Lite
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('KI analysiert jetzt das Video (das dauert ca. 1-2 Min)...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        upload_resp = client.files.upload(path=video_file)
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        
        while True:
            file_info = client.files.get(name=gfile_name)
            status = str(file_info.state).upper()
            if 'ACTIVE' in status: break
            time.sleep(15)
        
        prompt = """
        WICHTIG: Analysiere das beigefügte Video exakt. 
        Beschreibe die tatsächlichen Themen von HEUTE (aus dem Video). 
        Ignoriere dein Wissen von 2024. 
        Nutze Markdown mit Überschriften und visueller Beschreibung.
        """
        response = client.models.generate_content(model='gemini-3.1-flash-lite-preview', contents=[file_info, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        line1 = '---\ntitle: \"' + video_title + '\"\n'
        line2 = 'date: \"' + date_str + '\"\n'
        line3 = 'videoId: \"' + video_id + '\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(line1 + line2 + line3 + response.text)
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

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile_name)
        except: pass

if __name__ == '__main__':
    main()
