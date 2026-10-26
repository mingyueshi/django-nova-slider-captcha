"""Temporary, loopback-only UI fixture with actual component assets and host styles."""
import base64,io,json,os
import django
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlparse,parse_qs
from PIL import Image
ROOT=Path.cwd()
DJANGO=Path(django.__file__).parent/'contrib/admin/static/admin/css'
NOVA=Path(os.environ.get('NOVA_ADMIN_CSS', '../django-nova-admin/django-theme/src/nova_admin/static/nova_admin'))
def uri(size,color):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,format='PNG');return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
packet={'challengeId':'fixture','width':320,'height':160,'pieceWidth':44,'pieceY':40,'background':uri((320,160),(40,65,100)),'piece':uri((44,44),(230,175,80)),'expiresIn':600,'maxAttempts':5}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);host=q.get('host',['standalone'])[0];mode=q.get('mode',['auto'])[0];width=int(q.get('width',['240'])[0]);long=q.get('long',['0'])[0]=='1'
        assert host in ['standalone','django','nova'] and mode in ['auto','light','dark'] and 160<=width<=600
        attrs='' if mode=='auto' or host=='nova' else f' data-theme="{mode}"'
        body=f'class="nova-admin nova-mode-{mode}"' if host=='nova' else ''
        hostcss=''
        if host in ('django','nova'):hostcss=(DJANGO/'base.css').read_text()+(DJANGO/'dark_mode.css').read_text()
        if host=='nova':hostcss+=(NOVA/'theme.css').read_text()+(NOVA/'tokens.css').read_text()
        css=(ROOT/'src/nova_slider_captcha/static/nova_slider_captcha/slider.css').read_text()
        js=(ROOT/'src/nova_slider_captcha/static/nova_slider_captcha/slider.js').read_text()
        controls='<nav><a href="?host=standalone&mode=auto">Standalone</a> <a href="?host=django&mode=light">Django light</a> <a href="?host=django&mode=dark">Django dark</a> <a href="?host=nova&mode=light">Nova light</a> <a href="?host=nova&mode=dark">Nova dark</a></nav>'
        html='<!doctype html><html'+attrs+'><head><meta charset="utf-8"><title>Independent theme acceptance</title><style>'+hostcss+css+'''body{margin:0;padding:12px;box-sizing:border-box;font-family:system-ui}nav{margin-bottom:12px;overflow-wrap:anywhere}main{width:100%;max-width:'''+str(width)+'''px;background:var(--nova-panel,var(--body-bg,#fff));padding:8px;box-sizing:border-box}.case{margin-bottom:20px}h2{font-size:13px;margin:0 0 8px}body.standalone{color:#23283a;background:#f7f8fc}@media(prefers-color-scheme:dark){body.standalone{color:#e7edf5;background:#111722}body.standalone main{background:#1b2534}}html[data-theme="light"] body.standalone{color:#23283a;background:#f7f8fc}html[data-theme="light"] body.standalone main{background:#fff}html[data-theme="dark"] body.standalone{color:#e7edf5;background:#111722}html[data-theme="dark"] body.standalone main{background:#1b2534}</style></head><body '''+(body or ('class="standalone"' if host=='standalone' else ''))+'>'+controls+'<main>'+''.join('<section class="case"><h2>'+state+'</h2><nova-slider id="'+state+'" locale="en" field-name="'+state+'"></nova-slider></section>' for state in ['ready','success','error'])+'''</main><script>const packet='''+json.dumps(packet)+''';window.fetch=async(url)=>new Response(JSON.stringify(url.endsWith('init')?{csrfToken:'fixture'}:url.endsWith('challenge')?packet:{ok:true,token:'fixture-proof',expiresIn:60}),{headers:{'Content-Type':'application/json'}});</script><script>'''+js+'''</script><script>const timer=setInterval(()=>{const all=[...document.querySelectorAll('nova-slider')];if(all.every(w=>w.state==='ready')){clearInterval(timer);document.querySelector('#success').setState('success','success');document.querySelector('#error').setState('error','network_error');'''+('document.querySelector("#error").status.textContent="A very long verification failure message with retry instructions and a URLwithoutanybreaks012345678901234567890123456789";document.querySelector("#error .nsc-refresh-text").textContent="Get another verification puzzle with an unusually long label";' if long else '')+'''document.body.dataset.ready='yes';}},10);</script></body></html>'''
        encoded=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
HTTPServer(('127.0.0.1',8877),Handler).serve_forever()
