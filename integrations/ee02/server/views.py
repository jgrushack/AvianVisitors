"""Paper pages using the upstream stamp templates and typography."""
import html,json,math
import history
from urllib.parse import quote
MODES=['collage','stamps','most-heard','activity','first-seen']
TITLES={'collage':'Heard Today','stamps':'Avian Atlas','most-heard':'Most Heard','activity':'Bird Activity','first-seen':'First Detections'}
def esc(s):return html.escape(str(s))
def definitions():
 life=history.api('lifelist',{})['species']
 return [{'mode':m,'page':p,'title':TITLES[m]} for m in MODES for p in range(max(1,math.ceil(len(life)/6)) if m=='stamps' else 3 if m=='most-heard' else 2 if m=='activity' else max(1,math.ceil(min(50,len(life))/12)) if m=='first-seen' else 1)]
def page(mode,page):
 status=history.api('status',{});suffix='' if status['history_complete'] else ' · history importing'
 scripts=''.join('<script src="/app/'+s+'.js"></script>' for s in ['stamps','stamp-batch-root','stamp-batch-a','stamp-batch-b','stamp-batch-c'])
 css=''.join('<link rel="stylesheet" href="/app/'+s+'.css">' for s in ['styles','stamps','stamp-batch-root','stamp-batch-a','stamp-batch-b','stamp-batch-c'])
 body='';js='';subtitle='PUC-19176'
 if mode=='stamps':
  birds=sorted(history.api('lifelist',{})['species'],key=lambda b:b['first_seen'])
  dims=json.loads((history.ROOT/'avian-visitors/avian/frontend/dims.json').read_text())
  for i,b in enumerate(birds):b.update(index=i+1,count=b['n'],placeholder=history.birdweather.slugify(b['sci']) not in dims)
  birds=birds[page*6:page*6+6];body='<div class="album atlas-grid" id="album"></div>'
  js='const birds='+json.dumps(birds).replace('</','<\\/')+'''; document.querySelector('#album').innerHTML=birds.map(b=>'<div class="slot">'+STAMPS.markup(b,'/app/avian/api/cutout.php?sci='+encodeURIComponent(b.sci))+'</div>').join(''); STAMPS.syncFringe(document); if(window.FX) FX.run(document);'''
  subtitle='Life list · page '+str(page+1)+suffix
 elif mode=='most-heard':
  hours=[24,168,1000000][page%3];subtitle={24:'Past 24 hours',168:'Past 7 days',1000000:'All recorded history'}[hours]+suffix
  birds=history.api('recent',{'hours':hours})['species'][:12];total=max([b['n'] for b in birds],default=1)
  body='<ol class="ranking">'+''.join('<li><div><span>'+esc(b['com'])+'</span><strong>'+str(b['n'])+'</strong></div><div class="bar" style="width:'+str(100*b['n']/total)+'%"></div></li>' for b in birds)+'</ol>'
 elif mode=='first-seen':
  birds=history.api('firstseen',{'limit':50})['species'][page*12:page*12+12];subtitle='Newest additions · page '+str(page+1)+suffix
  body='<ol class="ranking">'+''.join('<li><div><span>'+esc(b['com'])+'</span><small>'+esc(b['first_seen'][:10])+'</small></div></li>' for b in birds)+'</ol>'
 elif mode=='activity':
  stats=history.api('stats',{});series=history.api('timeseries',{})
  subtitle=('Daily detections · past 30 days' if page==0 else 'Time of day · past 30 days')+suffix
  body='<div class="totals">'+''.join('<div><strong>'+str(stats[k]['detections'])+'</strong><span>'+label+'</span></div>' for k,label in [('today','today'),('week','past week'),('totals','all history')])+'</div>'
  rows=series['daily'] if page==0 else series['by_hour'];maximum=max([r['detections'] for r in rows],default=1) or 1
  body+='<div class="chart">'+''.join('<div class="column"><b>'+str(r['detections'])+'</b><i style="height:'+str(360*r['detections']/maximum)+'px"></i><span>'+esc(r['date'][5:] if page==0 else str(r['hour'])+':00')+'</span></div>' for r in rows)+'</div>'
 return '<!doctype html><meta charset="utf-8"><base href="/app/">'+css+'''<style>
html,body{margin:0;width:600px;height:800px;overflow:hidden;background:#efece0;color:#201f1b}*{box-sizing:border-box;animation:none!important;transition:none!important} main{position:relative;padding:30px 28px;height:800px}main>header{text-align:center;margin-bottom:25px}main>header p{font:italic 15px Georgia;margin:0 0 10px}main>header h1{font:normal 34px Georgia;letter-spacing:2px;text-transform:uppercase;margin:0 0 12px}main>header small{font:13px Georgia}.album{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,200px);gap:10px}.slot{display:flex;align-items:center;justify-content:center;overflow:visible}.slot .stamp-fit{transform:scale(.8);transform-origin:center}.ranking{padding:0;list-style:none;margin:0}.ranking li{padding:7px 0;border-bottom:1px solid #b4b0a4;font:18px/1.2 Georgia}.ranking li>div:first-child{display:flex;justify-content:space-between;gap:12px}.ranking strong{font-weight:normal}.ranking small{font-size:13px}.bar{height:5px;background:#333;margin-top:9px}.totals{display:flex;justify-content:space-around;margin:35px 0 60px}.totals strong{display:block;font:30px Georgia}.totals span{font:13px Georgia}.chart{display:flex;align-items:flex-end;gap:5px;height:460px;padding-bottom:60px}.column{flex:1;min-width:0;position:relative;display:flex;flex-direction:column;justify-content:flex-end;height:400px}.column i{display:block;background:#333;min-height:1px}.column b{font:9px Georgia;writing-mode:vertical-rl;margin-bottom:4px}.column span{position:absolute;top:410px;transform:rotate(65deg);transform-origin:left top;white-space:nowrap;font:10px Georgia}main>footer{position:absolute;bottom:15px;width:544px;text-align:center;font:11px Georgia}
</style><main><header><p>Avian Visitors</p><h1>'''+esc(TITLES[mode])+'</h1><small>'+esc(subtitle)+'</small></header>'+body+'<footer>'+esc('Latest detection '+str(status['last_detection'] or '')[:16])+'</footer></main>'+scripts+'<script>'+js+'''window.pageReady=false;(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));if(window.FX)FX.run(document);setTimeout(()=>window.pageReady=true,1500)})();</script>'''
