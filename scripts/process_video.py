import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir suchen NUR in den aktuellen Quellen, um Archiv-Leichen zu vermeiden
API_URLS = [
    'https://www.tagesschau.de/api2u/channels/',
    'https://www.tagesschau.de/api2u/homepage/',
    'https://www.tagesschau.de/api2u/news/'
]
CONTENT_DIR = 'content/summaries'

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    video_url = None
    video_title = None
    video_id = None
    
    # Wir nehmen das aktuelle Jahr als Filter
    current_year = str(datetime.now().year)
    print(f'Suche nach der aktuellsten 20-Uhr-Sendung aus {current_year}...')
    
    for url in API_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            # Wir suchen in allen Listen der API
            items = data.get('channels', []) + data.get('news', []) + data.get('items', [])
            
            for item in items:
                title = (item.get('title', '') or item.get('name', '') or '').lower()
                
                # KRITERIEN: 
                # 1. Muss "20:00" oder "20 Uhr" enthalten
                # 2. Muss "tagesschau" enthalten
                # 3. MUSS "2026" (aktuelles Jahr) enthalten, um altes Zeug zu ignorieren
                if 'tagesschau' in title and ('20:00' in title or '20 uhr' in title):
                    if current_year in title or 'heute' in title:
                        video_info = item.get('video') or item
                        streams = video_info.get('streams', {})
                        if streams:
                            video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                            video_title = item.get('title') or item.get('name')
                            video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                            print(f'Aktuelle Sendung gefunden: {video_title}')
                            break
            if video_url: break
        except Exception as e:
            print(f'Fehler bei {url}: {e}')

    if not video_url:
        print(f'Keine 20-Uhr-Sendung von {current_year} gefunden. Wir warten auf die Ausstrahlung!')
        return

    # Rest des Skripts wie gehabt...
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Diese Sendung haben wir schon.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print('Lade Video herunter...')
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini KI
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Gemini 3.1 Flash Lite arbeitet...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        upload_resp = client.files.upload(path=video_file)
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        
        while True:
            file_info = client.files.get(name=gfile_name)
            status = str(file_info.state).upper()
            if 'ACTIVE' in status: break
            elif 'FAILED' in status: sys.exit(1)
            time.sleep(10)
        
        prompt = 'Fasse die Sendung detailliert in Markdown zusammen mit Fokus auf die Kernthemen und visueller Beschreibung.'
        response = client.models.generate_content(model='gemini-3.1-flash-lite-preview', contents=[file_info, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        line1 = '---\ntitle: \"' + video_title + '\"\n'
        line2 = 'date: \"' + date_str + '\"\n'
        line3 = 'videoId: \"' + video_id + '\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(line1 + line2 + line3 + response.text)
        print('ERFOLG! Aktuelle Sendung gespeichert.')

        # 5. Email
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
