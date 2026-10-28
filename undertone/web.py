"""Shared listening page: a tiny HTTP server that mirrors what's playing to any browser on the LAN."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Undertone</title>
<style>
:root{--accent:#e5e5e8;--bg:#0b0b0f}
html,body{margin:0;height:100%;background:var(--bg);color:#eee;font-family:system-ui,sans-serif;overflow:hidden}
#bg{position:fixed;inset:0;background-size:cover;background-position:center;filter:blur(40px) brightness(.35);transform:scale(1.1)}
#wrap{position:relative;display:flex;flex-direction:column;height:100%;padding:24px 20px;box-sizing:border-box}
#head{display:flex;gap:16px;align-items:center}
#art{width:72px;height:72px;border-radius:10px;object-fit:cover;background:#222}
#title{font-weight:700;font-size:1.2rem}#meta{opacity:.6;font-size:.95rem}
#lines{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:14px;padding:0 8px}
.l{opacity:.35;font-size:1.15rem;transition:all .25s}.l.cur{opacity:1;color:var(--accent);font-weight:700;font-size:1.6rem}
.t{opacity:.55;font-size:.95rem;margin-top:-6px}
#idle{opacity:.5;text-align:center;margin:auto}
</style></head><body><div id="bg"></div><div id="wrap">
<div id="head"><img id="art" alt=""><div><div id="title"></div><div id="meta"></div></div></div>
<div id="lines"></div></div>
<script>
const $=id=>document.getElementById(id);
function render(s){
  document.documentElement.style.setProperty('--accent',s.accent||'#e5e5e8');
  if(!s.title){$('title').textContent='';$('meta').textContent='';$('lines').innerHTML='<div id="idle">Nothing playing</div>';return;}
  $('title').textContent=s.title;$('meta').textContent=s.artist+(s.album?' · '+s.album:'');
  const art=s.art?'/art?v='+encodeURIComponent(s.title):'';$('art').src=art;$('bg').style.backgroundImage=art?`url(${art})`:'';
  const lines=s.lines||[],i=s.idx,out=[];
  const lo=Math.max(0,i-3),hi=Math.min(lines.length,i+5);
  for(let k=lo;k<hi;k++){out.push(`<div class="l${k===i?' cur':''}">${esc(lines[k]||'♪')}</div>`);
    if(k===i&&s.translations&&s.translations[k])out.push(`<div class="t">${esc(s.translations[k])}</div>`);}
  if(!lines.length)out.push('<div id="idle">'+(s.lyrics==='instrumental'?'♪ Instrumental':'No lyrics')+'</div>');
  $('lines').innerHTML=out.join('');
}
const esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
new EventSource('/events').onmessage=e=>render(JSON.parse(e.data));
</script></body></html>
"""


def snapshot_payload(status, lines, idx, art_available, translations):
    t = status.get("track") or {}
    return {
        "title": t.get("title"), "artist": t.get("artist"), "album": t.get("album"),
        "position_s": status.get("position_s"), "lyrics": status.get("lyrics"),
        "lines": list(lines), "idx": idx, "translations": translations,
        "accent": status.get("accent"), "art": bool(art_available), "visible": status.get("visible"),
    }


class NowPlayingServer:
    def __init__(self, bind, port, get_payload, get_art, interval_s=0.25):
        self.get_payload, self.get_art, self.interval = get_payload, get_art, interval_s
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the UI process quiet
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/":
                    self._send(200, PAGE_HTML.encode(), "text/html; charset=utf-8")
                elif path == "/state":
                    self._send(200, json.dumps(outer.get_payload()).encode(), "application/json")
                elif path == "/art":
                    art = outer.get_art()
                    if art:
                        self._send(200, art[0], art[1])
                    else:
                        self._send(404, b"no art", "text/plain")
                elif path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    last = None
                    try:
                        while not outer._stop.is_set():
                            payload = outer.get_payload()
                            if payload != last:
                                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                                self.wfile.flush()
                                last = payload
                            time.sleep(outer.interval)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    self._send(404, b"not found", "text/plain")

        self._stop = threading.Event()
        self.httpd = ThreadingHTTPServer((bind, port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()
