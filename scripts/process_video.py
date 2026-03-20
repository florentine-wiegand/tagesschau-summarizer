import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

# Wir suchen gezielt nur in den aktuellsten Kanälen und der heutigen Startseite
API_URLS = [
    'https://www.tagesschau.de/api2u/news/?pageSize=50&searchText=20:00',
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
    print(f'Suche die 20-Uhr-Sendung aus {current_year}...')
    
    for url in API_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            items = data.get('news', []) + data.get('items', []) + data.get('results', []) + data.get('channels', [])
            
            for item in items:
                title = (item.get('title', '') or item.get('name', '') or '').lower()
                
                # Wir suchen nach "20:00" oder "20 Uhr", aber NICHT nach "100 sekunden"
                if 'tagesschau' in title and ('20:00' in title or '20 uhr' in title) and '100 sekunden' not in title:
                    if current_year in title or 'heute' in title:
                        video_info = item.get('video') or item
                        streams = video_info.get('streams', {})
                        if streams:
                            video_url = streams.get('h264m') or streams.get('h264s') or list(streams.values())[0]
                            video_title = item.get('title') or item.get('name')
                            video_id = item.get('externalId') or item.get('sophoraId') or f'ts_{int(time.time())}'
                            break
            if video_url: break
        except Exception as e:
            print(f'Fehler bei {url}: {e}')

    if not video_url:
        print(f'Keine 20-Uhr-Sendung von {current_year} gefunden.')
        return

    print(f'Gefunden! Verarbeite jetzt die echte 20-Uhr-Sendung: {video_title}')
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Schon verarbeitet.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    urllib.request.urlretrieve(video_url, video_file)

    # 3. Gemini KI
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Gemini 3.1 Flash Lite analysiert jetzt das echte Video...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        upload_resp = client.files.upload(path=video_file)
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        
        while True:
            file_info = client.files.get(name=gfile_name)
            status = str(file_info.state).upper()
            if 'ACTIVE' in status: break
            time.sleep(15)
        
        # DER VERBESSERTE PROMPT:
        prompt = """
        WICHTIG: Analysiere das beigefügte Video dieser Nachrichtensendung EXAKT. 
        Beschreibe die tatsächlichen Beiträge, die in DIESER Sendung vorkommen. 
        Ignoriere dein internes Wissen über vergangene Jahre (wie 2024). 
        Stelle für jeden Beitrag die Kernthemen dar und beschreibe kurz die visuellen Szenen im Video.
        Nutze Markdown, Überschriften und Listen für eine professionelle Optik.
        """
        response = client.models.generate_content(model='gemini-3.1-flash-lite-preview', contents=[file_info, prompt])
        
        # 4. Speichern
        date_str = datetime.now().strftime('%Y-%m-%d')
        line1 = '---\ntitle: \"' + video_title + '\"\n'
        line2 = 'date: \"' + date_str + '\"\n'
        line3 = 'videoId: \"' + video_id + '\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(line1 + line2 + line3 + response.text)
        print('DATEI ERFOLGREICH GESPEICHERT!')

        # 5. Email Newsletter
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

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile_name)
        except: pass

if __name__ == '__main__':
    main()
