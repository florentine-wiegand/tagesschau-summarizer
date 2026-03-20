import os
import json
import urllib.request
import time
from datetime import datetime
from google import genai
import resend
import markdown

CONTENT_DIR = 'content/summaries'

def find_broadcast():
    url = 'https://www.tagesschau.de/api2u/channels/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
    
    best_match = None
    best_date = None
    
    for item in data.get('channels', []):
        title = (item.get('title', '') or '').lower().strip()
        date_str = item.get('date', '')
        content = item.get('content', [])
        
        if title == 'tagesschau' and date_str and content:
            print(f'Kandidat: {item.get("title")} vom {date_str}')
            if best_date is None or date_str > best_date:
                best_date = date_str
                best_match = item
    
    return best_match, best_date

def main():
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print('Suche nach der aktuellsten Tagesschau-Sendung...')
    item, broadcast_date = find_broadcast()
    
    if not item:
        print('Keine Sendung gefunden.')
        return
    
    video_title = item.get('title', 'tagesschau')
    video_id = item.get('sophoraId') or item.get('externalId') or f'ts_{int(time.time())}'
    broadcast_date = broadcast_date or ''
    schlagzeilen = item.get('content', [])
    
    # Video-Links aus der API holen
    streams = item.get('streams', {})
    video_stream_url = streams.get('h264m') or streams.get('h264s') or ''
    detail_url = item.get('detailsweb') or ''
    
    print(f'Gefunden: {video_title} vom {broadcast_date}')
    
    md_filename = os.path.join(CONTENT_DIR, f'{video_id}.md')
    if os.path.exists(md_filename):
        print('Schon verarbeitet.')
        return
    
    # Schlagzeilen als Text zusammenstellen
    schlagzeilen_text = '\n'.join(
        f'- {s["value"]}' for s in schlagzeilen if s.get('type') == 'text'
    )
    
    # Gemini: Zusammenfassung aus den Schlagzeilen
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    print('Gemini generiert Zusammenfassung...')
    
    client = genai.Client(api_key=gemini_api_key)
    
    prompt = (
        'Du bist ein professioneller Nachrichtenredakteur. '
        'Aus der Tagesschau-Sendung vom ' + broadcast_date[:10] + ' gibt es folgende Schlagzeilen:\n\n'
        + schlagzeilen_text + '\n\n'
        'Erstelle daraus eine informative, gut strukturierte Zusammenfassung im Markdown-Format. '
        'Nutze Ueberschriften fuer jedes Thema und erklaere den Hintergrund fachkundig. '
        'Schreibe auf Deutsch.'
    )
    
    response = client.models.generate_content(model='gemini-3.1-flash-lite-preview', contents=prompt)
    
    # Speichern (jetzt mit videoUrl und detailUrl im Frontmatter)
    date_formatted = datetime.now().strftime('%Y-%m-%d')
    line1 = '---\ntitle: \"' + video_title + ' vom ' + broadcast_date[:10] + '\"\n'
    line2 = 'date: \"' + date_formatted + '\"\n'
    line3 = 'videoId: \"' + video_id + '\"\n'
    line4 = 'videoUrl: \"' + video_stream_url + '\"\n'
    line5 = 'detailUrl: \"' + detail_url + '\"\n---\n\n'
    
    with open(md_filename, 'w', encoding='utf-8') as f:
        f.write(line1 + line2 + line3 + line4 + line5 + response.text)
    print('DATEI ERFOLGREICH GESPEICHERT!')
    
    # E-Mail
    resend_api_key = os.environ.get('RESEND_API_KEY')
    email_to = os.environ.get('EMAIL_TO')
    if resend_api_key and email_to:
        resend.api_key = resend_api_key
        
        # Video-Link in der E-Mail einbauen
        video_link_html = ''
        if detail_url:
            video_link_html = f'<p><a href="{detail_url}" style="background:#0057a8;color:white;padding:10px 20px;border-radius:5px;text-decoration:none;">▶ Video auf tagesschau.de ansehen</a></p><br>'
        elif video_stream_url:
            video_link_html = f'<p><a href="{video_stream_url}" style="background:#0057a8;color:white;padding:10px 20px;border-radius:5px;text-decoration:none;">▶ Video direkt ansehen</a></p><br>'
        
        resend.Emails.send({
            'from': 'Tagesschau KI <onboarding@resend.dev>',
            'to': [email_to],
            'subject': f'KI-Zusammenfassung: Tagesschau vom {broadcast_date[:10]}',
            'html': f'<h2>Tagesschau vom {broadcast_date[:10]}</h2>' + video_link_html + markdown.markdown(response.text)
        })
        print('Email mit Video-Link versendet!')

if __name__ == '__main__':
    main()
