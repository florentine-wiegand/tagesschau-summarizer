import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown
import sys

CONTENT_DIR = 'content/summaries'

def find_video():
    # Die /channels/ API listet alle Sendungen mit korrekten Streams
    url = 'https://www.tagesschau.de/api2u/channels/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
    
    channels = data.get('channels', [])
    print(f'{len(channels)} Eintraege in der Kanalliste gefunden.')
    
    best_match = None
    best_date = None
    
    for item in channels:
        title = (item.get('title', '') or '').lower().strip()
        date_str = item.get('date', '')
        streams = item.get('streams', {})
        
        # Wir suchen nur nach "tagesschau" (nicht "tagesschau24" und nicht "100 sekunden")
        is_main = (title == 'tagesschau') and ('100' not in title)
        
        # Die Sendung muss einen direkten MP4-Stream haben (kein Livestream)
        has_mp4 = streams.get('h264m') or streams.get('h264s')
        
        if is_main and date_str and has_mp4:
            print(f'Kandidat: {item.get("title")} vom {date_str}')
            # Wir nehmen die NEUSTE Sendung (mit dem groessten Datum)
            if best_date is None or date_str > best_date:
                best_date = date_str
                best_match = item
    
    return best_match

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print('Suche nach der aktuellsten Tagesschau-Sendung...')
    item = find_video()
    
    if not item:
        print('Keine passende Sendung in der Kanalliste gefunden.')
        return
    
    video_title = item.get('title', 'tagesschau')
    video_id = item.get('sophoraId') or item.get('externalId') or f'ts_{int(time.time())}'
    date_str = item.get('date', '')
    streams = item.get('streams', {})
    video_url = streams.get('h264m') or streams.get('h264s')
    
    print(f'Gefunden: {video_title} vom {date_str}')
    print(f'Stream-URL: {video_url}')
    
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Diese Sendung ist schon verarbeitet.')
        return

    # 2. Download
    video_file = 'current_video.mp4'
    print('Lade Video herunter...')
    urllib.request.urlretrieve(video_url, video_file)
    print(f'Download fertig! Dateigroesse: {os.path.getsize(video_file)} Bytes')

    # 3. Gemini KI
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Lade Video bei Gemini hoch...')
    try:
        client = genai.Client(api_key=gemini_api_key)
        upload_resp = client.files.upload(path=video_file)
        gfile_name = upload_resp if isinstance(upload_resp, str) else upload_resp.name
        print(f'Upload fertig. Dateiname: {gfile_name}')
        
        # Warten auf Verarbeitung
        while True:
            file_info = client.files.get(name=gfile_name)
            status = str(file_info.state).upper()
            if 'ACTIVE' in status: break
            print(f'Status: {status}... warte.')
            time.sleep(15)
        
        print('KI generiert die Zusammenfassung...')
        prompt = (
            'Analysiere dieses Nachrichtenvideo exakt. '
            'Beschreibe die tatsaechlichen Themen aus dem Video (nicht aus deinem Gedaechtnis). '
            'Nutze Markdown mit Ueberschriften und visueller Beschreibung.'
        )
        response = client.models.generate_content(model='gemini-3.1-flash-lite-preview', contents=[file_info, prompt])
        
        # 4. Speichern
        date_formatted = datetime.now().strftime('%Y-%m-%d')
        line1 = '---\ntitle: \"' + video_title + '\"\n'
        line2 = 'date: \"' + date_formatted + '\"\n'
        line3 = 'videoId: \"' + video_id + '\"\n---\n\n'
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(line1 + line2 + line3 + response.text)
        print('DATEI ERFOLGREICH GESPEICHERT!')

        # 5. E-Mail
        resend_api_key = os.environ.get('RESEND_API_KEY')
        email_to = os.environ.get('EMAIL_TO')
        if resend_api_key and email_to:
            resend.api_key = resend_api_key
            resend.Emails.send({
                'from': 'Tagesschau KI <onboarding@resend.dev>',
                'to': [email_to],
                'subject': f'KI-Zusammenfassung: {video_title} vom {date_str[:10]}',
                'html': markdown.markdown(response.text)
            })
            print('Email versendet!')

    finally:
        if os.path.exists(video_file): os.remove(video_file)
        try: client.files.delete(name=gfile_name)
        except: pass

if __name__ == '__main__':
    main()
