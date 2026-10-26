import base64,io,json
from pathlib import Path
from PIL import Image,ImageDraw
root=Path.cwd()
def uri(size,mode,color):
    image=Image.new(mode,size,color)
    out=io.BytesIO(); image.save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
packet={'challengeId':'integration-geometry','width':480,'height':200,'pieceWidth':60,'pieceY':40,'background':uri((480,200),'RGB',(40,65,100)),'piece':uri((60,60),'RGBA',(245,180,80,255)),'expiresIn':120,'maxAttempts':5}
html='''<!doctype html><meta charset="utf-8"><title>Independent geometry and form names</title><style>body{margin:24px;font-family:sans-serif}form{max-width:600px}nova-slider{margin-bottom:28px}</style><style>'''+(root/'src/nova_slider_captcha/static/nova_slider_captcha/slider.css').read_text()+'''</style><script>
const packet='''+json.dumps(packet)+''';
window.calls=[];
window.fetch=async(url,options={})=>{window.calls.push({url,body:options.body?JSON.parse(options.body):null});return new Response(JSON.stringify(url.endsWith('init')?{csrfToken:'review'}:url.endsWith('challenge')?packet:{ok:true,token:'proof-'+window.calls.length,expiresIn:60}),{headers:{'Content-Type':'application/json'}})};
</script><script>'''+(root/'src/nova_slider_captcha/static/nova_slider_captcha/slider.js').read_text()+'''</script><form><nova-slider id="first" purpose="signup" field-name="join-security" locale="en"></nova-slider><nova-slider id="second" purpose="reset" field-name="recover-security" locale="en" style="--nsc-handle-size:56px"></nova-slider></form>'''
Path(__file__).with_name('geometry.html').write_text(html)
print('Prepared local browser fixture, real 480x200 and 60x60 PNGs, mocked HTTP.')
