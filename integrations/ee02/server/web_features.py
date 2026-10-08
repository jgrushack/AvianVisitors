import json,mimetypes,re,threading,io,hashlib,urllib.request,fcntl,subprocess,tempfile
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
import history,views
LOCK=threading.RLock()
AUDIO_LOCK=threading.Lock()
AUDIO_CACHE_LIMIT=256 * 1024 * 1024

def prune_audio(cache,limit=AUDIO_CACHE_LIMIT):
 # mtime is refreshed on use, giving least-recently-used eviction.
 files=[(p.stat().st_mtime,p.stat().st_size,p) for p in cache.iterdir()
        if p.is_file() and p.suffix in ('.flac','.wav')]
 total=sum(size for _,size,_ in files)
 for _,size,p in sorted(files):
  if total<=limit:break
  p.unlink();total-=size
 return total

def recording_bytes(data,r,atomic):
 # Serialize download/conversion/eviction; never delete another request's input.
 cache=data/'audio';cache.mkdir(exist_ok=True)
 with AUDIO_LOCK:
  prune_audio(cache)
  try:
   clip=cache/(str(r['id'])+'.wav')
   if not clip.exists():
    url=r['audio'];file=cache/(hashlib.sha256(url.encode()).hexdigest()+'.flac')
    if not file.exists():
     with urllib.request.urlopen(url,timeout=30) as response:body=response.read(15_000_001)
     if len(body)>15_000_000:raise ValueError('Recording too large')
     atomic(file,body)
    file.touch()
    start=max(0,float(r['start'] or 0));duration=max(.1,float(r['end'] or start+3)-start)
    if duration>120:raise ValueError('Unexpected recording duration')
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
     out=Path(tmp)/'clip.wav'
     subprocess.run(['ffmpeg','-v','error','-nostdin','-ss',str(start),'-i',str(file),'-t',str(duration),'-ac','1','-ar','32000',str(out)],check=True,timeout=30)
     atomic(clip,out.read_bytes())
   clip.touch()
   return clip.read_bytes()
  finally:prune_audio(cache)


def state(data):
 try:return json.loads((data/'selection.json').read_text())
 except FileNotFoundError:return {'mode':'collage','page':0,'events':[]}

def select(data,atomic,command):
 if not isinstance(command,dict):raise ValueError('Expected an object')
 if command.get('action','') not in ('','mode','next','previous'):raise ValueError('Unknown action')
 if 'event' in command and not isinstance(command['event'],str):raise ValueError('Invalid event')
 if 'page' in command and (not isinstance(command['page'],int) or isinstance(command['page'],bool)):raise ValueError('Invalid page')
 with LOCK, open(data/'selection.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  catalog=json.loads((data/'catalog.json').read_text());s=state(data)
  event=command.get('event')
  if event and event in s.get('events',[]):return s
  mode=command.get('mode',s['mode']);page=int(command.get('page',s['page']))
  if command.get('action')=='mode':mode=views.MODES[(views.MODES.index(s['mode'])+1)%len(views.MODES)];page=0
  available=[v for v in catalog if v['mode']==mode]
  if not available:raise ValueError('Mode is not ready')
  if command.get('action')=='next':page+=1
  if command.get('action')=='previous':page-=1
  page%=len(available)
  m=available[page];s.update(mode=mode,page=page,events=(s.get('events',[])+([event] if event else []))[-50:])
  atomic(data/'selection.json',json.dumps(s).encode());atomic(data/'manifest.json',json.dumps(m).encode())
  return s

def routes(h,root,data,atomic):
 u=urlsplit(h.path);p={k:v[-1] for k,v in parse_qs(u.query).items()};path=u.path
 def send(body,kind='application/json',status=200,cache=False):
  if not isinstance(body,bytes):body=(json.dumps(body) if kind=='application/json' else body).encode()
  cache=cache or kind not in ('application/json','text/html')
  etag='"'+hashlib.sha256(body).hexdigest()+'"' if cache and status==200 else None
  if etag and h.headers.get('If-None-Match')==etag:
   h.send_response(304);h.send_header('ETag',etag);h.send_header('Cache-Control','private, no-cache');h.end_headers();return True
  h.send_response(status);h.send_header('Content-Type',kind);h.send_header('Content-Length',str(len(body)));h.send_header('Cache-Control','private, no-cache' if etag else 'no-store')
  if etag:h.send_header('ETag',etag)
  h.end_headers()
  if h.command != "HEAD":h.wfile.write(body)
  return True
 if h.command=='POST':
  if path not in ['/control','/device','/diagnostics']:return False
  origin=h.headers.get('Origin')
  if origin and urlsplit(origin).netloc!=h.headers.get('Host'):return send({'error':'Origin mismatch'},status=403)
  try:
   n=int(h.headers.get('Content-Length',0))
   if not 0<n<=4096:return send({'error':'Invalid body'},status=400)
   command=json.loads(h.rfile.read(n))
   if not isinstance(command,dict):raise ValueError('Expected an object')
   if path=='/diagnostics':
    atomic(data/'diagnostics.json',json.dumps({'received_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'device':command}).encode());return send({'ok':True})
   s=select(data,atomic,command)
   if path=='/device':atomic(data/'device.json',json.dumps({'last_seen':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),**{k:command[k] for k in ['battery_voltage','wake_reason','displayed_version','action'] if k in command}}).encode())
   return send(s)
  except (ValueError,TypeError,KeyError,FileNotFoundError) as e:return send({'error':str(e)},status=400)
 if path=='/':
  return send('''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Avian Visitors — Frame</title><style>body{max-width:950px;margin:30px auto;padding:0 20px;background:#efece0;color:#222;font:18px Georgia}button,select{font:inherit;padding:10px;margin:5px}img{max-width:100%;max-height:75vh}a{color:inherit}#status{font-size:15px}</style><h1>Avian Visitors</h1><p><a href="/app/">Open stamps, statistics & recordings →</a></p><select id="mode"><option value="collage">Heard Today</option><option value="stamps">Stamp Collection</option><option value="most-heard">Most Heard</option><option value="activity">Activity</option><option value="first-seen">First Detections</option></select><button onclick="change({action:'previous'})">← Previous</button><button onclick="change({action:'next'})">Next →</button><p id="status"></p><img id="preview" src="/preview.png"><script>async function refresh(){let s=await(await fetch('/controls.json')).json();mode.value=s.selection.mode;document.getElementById('status').textContent='Page '+(s.selection.page+1)+' · '+(s.history.history_complete?'History synced':('Importing history: '+s.history.records+' records'))+(s.device?' · Last device check-in: '+new Date(s.device.last_seen).toLocaleString():'');preview.src='/preview.png?t='+Date.now()}async function change(c){let r=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});if(!r.ok)alert((await r.json()).error);await refresh()}mode.onchange=()=>change({mode:mode.value,page:0});refresh();setInterval(refresh,60000);</script>''','text/html')
 if path=='/controls.json':
  return send({'selection':state(data),'history':history.api('status',{}),'device':json.loads((data/'device.json').read_text()) if (data/'device.json').exists() else None})
 if path=='/display':
  mode=p.get('mode','stamps');page=int(p.get('page',0))
  if mode not in views.MODES or mode=='collage' or page<0:return send({'error':'Invalid page'},status=400)
  return send(views.page(mode,page),'text/html')
 if path=='/app/avian/api/menu.php':
  return send({'items':[{'label':'Frame controls','href':'/','native':True}], 'auth':{'required':False,'lan_policy':True}})
 if path=='/app/avian/api/bundle-assets.php':
  front=root/'avian-visitors/avian/frontend'
  dims=json.loads((front/'dims.json').read_text());masks=json.loads((front/'masks.json').read_text())
  return send({'ok':True,'active':{'id':'official-western-us-woodblock','version':'1.0.0','revision':'included-woodblock-v1','content_revision':'0'*64,'included':True,'name':'Japanese Woodblock','species_count':len({re.sub('-2$','',k) for k in dims}),'pose_count':len(dims)},'dims':dims,'masks':masks},cache=True)
 if '/avian/api/birdnet-api.php' in path:
  try:return send(history.api(p.get('action','recent'),p))
  except ValueError as e:return send({'error':str(e)},status=400)
 if '/avian/api/cutout.php' in path:
  slug=re.sub('[^a-z0-9]+','-',p.get('sci','').lower()).strip('-');art=root/'avian-visitors/avian/assets/illustrations';file=art/(slug+('-2' if p.get('pose')=='2' else '')+'.png')
  if not file.exists():file=art/(slug+'.png')
  if not file.exists():
   dims=json.loads((root/'avian-visitors/avian/frontend/dims.json').read_text())
   if slug in dims:
    cache=data/'illustrations';cache.mkdir(exist_ok=True)
    name=slug+('-2' if p.get('pose')=='2' and slug+'-2' in dims else '')+'.png'
    file=cache/name
    if not file.exists():
     with urllib.request.urlopen('https://raw.githubusercontent.com/Twarner491/AvianVisitors/2f18a66676b85d9548cfcbca21d94a4aab88e17a/avian/assets/illustrations/'+name,timeout=45) as response:raw=response.read(20_000_001)
     if len(raw)>20_000_000:raise ValueError('Artwork too large')
     from PIL import Image
     with Image.open(io.BytesIO(raw)) as im:im.verify()
     atomic(file,raw)
   else:file=root/'avian-visitors/avian/frontend/nest-eggs.webp'
  return send(file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'image/png')
 if '/avian/api/recording' in path:
  c=history.db()
  try:
   r=c.execute('SELECT id,audio,start,end FROM detections WHERE id=?',(p.get('detection',''),)).fetchone()
   if not r:r=c.execute('SELECT id,audio,start,end FROM detections WHERE sci=? AND audio IS NOT NULL ORDER BY confidence DESC LIMIT 1',(p.get('sci',''),)).fetchone()
  finally:c.close()
  if not r or not r['audio']:return send({'error':'Recording unavailable'},status=404)
  url=r['audio']
  if urlsplit(url).hostname!='media.birdweather.com':return send({'error':'Unexpected audio host'},status=502)
  return send(recording_bytes(data,r,atomic),'audio/wav')
 if '/avian/api/wiki.php' in path:
  import birdweather
  sci=p.get('sci','');cache=data/'descriptions';cache.mkdir(exist_ok=True);file=cache/(hashlib.sha256(sci.encode()).hexdigest()+'.json')
  if not file.exists():
   species=birdweather._graphql('query($s:String!){species(scientificName:$s){wikipediaSummary wikipediaUrl}}',20,variables={'s':sci},strict=True)['data']['species'] or {}
   atomic(file,json.dumps({'extract':species.get('wikipediaSummary') or '', 'source':{'url':species.get('wikipediaUrl') or ''}}).encode())
  return send(file.read_bytes())
 # Upstream stamp templates load decorative art outside the frontend tree.
 for prefix in ('/app/avian/assets/references/', '/avian/assets/references/'):
  if path.startswith(prefix):
   base=(root/'avian-visitors/avian/assets/references').resolve()
   file=(base/path[len(prefix):]).resolve()
   if not file.is_relative_to(base) or not file.is_file():return send({'error':'Not found'},status=404)
   return send(file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream',cache=True)
 if path.startswith('/avian/frontend/'):
  path='/app/'+path[len('/avian/frontend/'):]
 if path.startswith('/app/'):

  rel=path[len('/app/'):] or 'index.html';base=(root/'avian-visitors/avian/frontend').resolve();file=(base/rel).resolve()
  if not file.is_relative_to(base) or not file.is_file():return send({'error':'Not found'},status=404)
  return send(file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream',cache=True)
 return False

def catalog(root,data,atomic,publish,collage):
 from playwright.sync_api import sync_playwright
 from PIL import Image
 entries=[dict(collage,mode='collage',page=0,title='Heard Today')]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page(viewport={'width':600,'height':800},device_scale_factor=2)
  failed_assets=[]
  page.on('response',lambda r: failed_assets.append((r.status,r.url)) if r.status>=400 else None)
  page.on('requestfailed',lambda r: failed_assets.append(('network',r.url)))
  for d in views.definitions():
   if d['mode']=='collage':continue
   failed_assets.clear()
   page.goto('http://127.0.0.1:8080/display?mode='+d['mode']+'&page='+str(d['page']),wait_until='networkidle')
   page.wait_for_function('window.pageReady===true',timeout=30000)
   broken=page.evaluate('Array.from(document.images).filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src)')
   if broken or failed_assets:raise RuntimeError('Stamp assets failed: '+str(broken+failed_assets))
   overflow=page.locator('.ranking,.chart,.totals,.stamp,main>header,main>footer').evaluate_all('(els)=>els.filter(e=>{const r=e.getBoundingClientRect();return r.x<8||r.right>592||r.y<10||r.bottom>790}).map(e=>e.className||e.tagName)')
   if overflow:raise RuntimeError('Page exceeds mat-safe bounds: '+str(d)+' '+str(overflow))
   buf=page.screenshot()
   with Image.open(io.BytesIO(buf)) as im:m=publish(im,'ready',[],activate=False)
   entries.append(dict(m,**d))
  browser.close()
 with LOCK, open(data/'selection.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  atomic(data/'catalog.json',json.dumps(entries).encode())
 select(data,atomic,{})
