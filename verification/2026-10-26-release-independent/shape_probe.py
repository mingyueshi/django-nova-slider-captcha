"""Local-only baseline: no requests, tokens, sessions, or external targets."""
import base64,io,json,time
from PIL import Image,ImageFilter
from nova_slider_captcha.images import make_puzzle

def decode(uri):return Image.open(io.BytesIO(base64.b64decode(uri.split(',',1)[1])))
correct=0;timings=[];samples=24
for _ in range(samples):
    expected,y,background,piece=make_puzzle()
    bg=decode(background).convert('RGB');alpha=decode(piece).getchannel('A');inner=alpha.filter(ImageFilter.MinFilter(3))
    edge=[(x,j) for j in range(alpha.height) for x in range(alpha.width) if alpha.getpixel((x,j))>inner.getpixel((x,j))]
    started=time.perf_counter()
    scores=[sum(bg.getpixel((x+dx,y+dy))==(206,248,251) for dx,dy in edge) for x in range(bg.width-alpha.width+1)]
    predicted=max(range(len(scores)),key=scores.__getitem__)
    timings.append((time.perf_counter()-started)*1000)
    correct+=predicted==expected
print(json.dumps({'status':'completed','samples':samples,'exact_coordinate_matches':correct,'mean_match_ms':sum(timings)/len(timings),'method':'Use response piece alpha contour and public pieceY; correlate the renderer\'s fixed highlight border across the response background. No fixed shape template is needed.','limitations':['Small local baseline on current procedural images only.','This does not measure every solver or a proposed shape-library implementation.','No public endpoint was requested.']},indent=2))
