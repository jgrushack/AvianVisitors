"""Station-scoped BirdWeather archive and AvianVisitors read API."""
import json, os, sqlite3, sys, time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
ROOT=Path(os.environ.get('BIRD_ROOT','/opt/bird-renderer'))
DATA=Path(os.environ.get('BIRD_DATA','/var/lib/bird-renderer'))
sys.path.insert(0,str(ROOT/'avian-visitors/frame'))
import birdweather
TZ=ZoneInfo('America/New_York')

def db():
 DATA.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DATA/'history.sqlite',timeout=30);c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL')
 c.executescript('''CREATE TABLE IF NOT EXISTS detections(id TEXT PRIMARY KEY,ts REAL,local TEXT,sci TEXT,com TEXT,confidence REAL,audio TEXT,start REAL,end REAL,species_id TEXT);
 CREATE INDEX IF NOT EXISTS det_ts ON detections(ts); CREATE INDEX IF NOT EXISTS det_sci ON detections(sci,ts);
 CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);''')
 return c

def meta(c,key,default=None):
 r=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return json.loads(r[0]) if r else default

def put(c,key,value):c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value)))

def sync():
 import fcntl
 with open(DATA/'history.lock','w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  c=db();sid=json.loads(Path('/etc/bird-renderer/config.json').read_text())['station_id']
  st=birdweather._graphql('query($id:ID!){station(id:$id){id name timezone earliestDetectionAt}}',30,variables={'id':sid},strict=True)['data']['station']
  if st['id']!=sid:raise ValueError('Wrong station')
  put(c,'station',st);c.commit()
  complete=meta(c,'complete',False);cursor=None if complete else meta(c,'cursor')
  latest=c.execute('SELECT MAX(ts) FROM detections').fetchone()[0]
  start=(datetime.fromtimestamp(latest,TZ)-timedelta(days=1)).date().isoformat() if complete and latest else st['earliestDetectionAt'][:10]
  period={'from':start,'to':(datetime.now(TZ)+timedelta(days=1)).date().isoformat(),'timezone':st['timezone']}
  query='''query($ids:[ID!]!,$period:InputDuration!,$cursor:String){detections(stationIds:$ids,period:$period,first:500,after:$cursor){totalCount nodes{id timestamp confidence species{id commonName scientificName} soundscape{url startTime endTime}} pageInfo{hasNextPage endCursor}}}'''
  pages=0
  while True:
   for attempt in range(4):
    try:
     result=birdweather._graphql(query,45,variables={'ids':[sid],'period':period,'cursor':cursor},strict=True)['data']['detections'];break
    except birdweather.BirdWeatherError:
     if attempt==3:raise
     time.sleep(2**attempt)

   for d in result['nodes']:
    if not d['timestamp'] or not d['species']['scientificName']:continue
    dt=datetime.fromisoformat(d['timestamp']);s=d['species'];a=d.get('soundscape') or {}
    c.execute('INSERT OR REPLACE INTO detections VALUES(?,?,?,?,?,?,?,?,?,?)',(d['id'],dt.timestamp(),dt.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S'),s['scientificName'],s['commonName'],d['confidence'],a.get('url'),a.get('startTime'),a.get('endTime'),s['id']))
   cursor=result['pageInfo']['endCursor'];pages+=1
   if not complete:put(c,'cursor',cursor)
   put(c,'updated_at',datetime.now(TZ).isoformat());put(c,'expected',result['totalCount'] if not complete else meta(c,'expected',0));c.commit()
   if pages%10==0:print('History imported',c.execute('SELECT COUNT(*) FROM detections').fetchone()[0],flush=True)
   if not result['pageInfo']['hasNextPage']:
    put(c,'complete',True);put(c,'cursor',None);c.commit();break
  print('Sync complete:',c.execute('SELECT COUNT(*) FROM detections').fetchone()[0],flush=True)

def api(action,p):
 c=db()
 try:return _api(c,action,p)
 finally:c.close()

def _api(c,action,p):
 now=datetime.now(TZ);date=p.get('date',now.date().isoformat());day=datetime.strptime(date,'%Y-%m-%d').replace(tzinfo=TZ)
 anchor=now if date==now.date().isoformat() else day+timedelta(days=1)-timedelta(microseconds=1)
 hours=max(1,min(1000000,int(p.get('hours',24))));start=max(0,anchor.timestamp()-hours*3600)
 ctx={'date':date,'station_date':now.date().isoformat(),'is_today':date==now.date().isoformat(),'anchor':anchor.strftime('%Y-%m-%d %H:%M:%S'),'as_of':meta(c,'updated_at'),'history_complete':meta(c,'complete',False)}
 def rows(q,args=()):return [dict(r) for r in c.execute(q,args)]
 def counts(lo=0,hi=None):return rows('SELECT COUNT(*) detections,COUNT(DISTINCT sci) species FROM detections WHERE ts>=? AND ts<=?',(lo,hi or anchor.timestamp()))[0]
 def species(where='1',args=()):return rows('SELECT sci,com,COUNT(*) n,MIN(local) first_seen,MAX(local) last_seen,MAX(confidence) best_conf FROM detections WHERE '+where+' GROUP BY sci ORDER BY n DESC',args)
 if action=='status':return {**ctx,'station':meta(c,'station'),'records':counts(0,time.time())['detections'],'expected':meta(c,'expected'),'last_detection':c.execute('SELECT MAX(local) FROM detections').fetchone()[0]}
 if action in ('recent','lifelist','firstseen'):
  sp=species('ts BETWEEN ? AND ?',(start,anchor.timestamp())) if action=='recent' else species('ts<=?',(anchor.timestamp(),))
  for s in sp:
   best=c.execute('SELECT id,local FROM detections WHERE sci=? AND ts BETWEEN ? AND ? ORDER BY confidence DESC LIMIT 1',(s['sci'],start if action=='recent' else 0,anchor.timestamp())).fetchone()
   s.update(total=s['n'],top_file=best['id'],detection_id=int(best['id']),top_at=best['local'])
  if action=='firstseen':sp=sorted(sp,key=lambda s:s['first_seen'],reverse=True)[:int(p.get('limit',10))]
  return {**ctx,'hours':hours,'species':sp,'site_name':'PUC-19176','midnight_clamped':False,'reset_at_midnight':False}
 if action=='stats':return {**ctx,'totals':counts(),'today':counts(day.timestamp()),'week':counts(anchor.timestamp()-168*3600),'last_hour':counts(anchor.timestamp()-3600),'started':c.execute('SELECT MIN(local) FROM detections').fetchone()[0]}
 if action in ('timeseries','calendar'):
  days=max(1,min(90,int(p.get('days',30))))
  daily=rows('SELECT substr(local,1,10) date,COUNT(*) detections,COUNT(DISTINCT sci) species FROM detections WHERE local>=? AND ts<=? GROUP BY date ORDER BY date',('0000' if action=='calendar' else (day-timedelta(days=days-1)).date().isoformat(),anchor.timestamp()))
  first_date=daily[0]['date'] if daily else None;last_date=daily[-1]['date'] if daily else None
  by_hour=rows('SELECT CAST(substr(local,12,2) AS INT) hour,COUNT(*) detections FROM detections WHERE ts BETWEEN ? AND ? GROUP BY hour',(anchor.timestamp()-30*86400,anchor.timestamp()))
  if action=='timeseries':
   observed={r['date']:r for r in daily}
   dates=[(day-timedelta(days=i)).date().isoformat() for i in range(days-1,-1,-1)]
   daily=[observed.get(d,{'date':d,'detections':0,'species':0}) for d in dates]
   observed_hours={r['hour']:r for r in by_hour}
   by_hour=[observed_hours.get(h,{'hour':h,'detections':0}) for h in range(24)]
  return {**ctx,'days':daily if action=='calendar' else days,'daily':daily,'first_date':first_date,'last_date':last_date,'by_hour':by_hour}
 if action=='hourly':
  sp=species('substr(local,1,10)=?',(date,))[:int(p.get('limit',30))]
  for s in sp:s.update(total=s['n'],hours=rows('SELECT CAST(substr(local,12,2) AS INT) hour,COUNT(*) n FROM detections WHERE sci=? AND substr(local,1,10)=? GROUP BY hour',(s['sci'],date)))
  return {**ctx,'anchor_hour':anchor.hour,'species':sp}
 if action=='rhythm':
  week=hours==168;lo=anchor.timestamp()-168*3600 if week else day.timestamp();hi=anchor.timestamp();prevlo=lo-7*86400
  slot='(CAST(substr(local,12,2) AS INT)*60+CAST(substr(local,15,2) AS INT))'
  now_slot=anchor.hour*60+anchor.minute
  return {**ctx,'days':7,'hours':hours,'mode':'week' if week else 'day','slots':1440,'now_slot':1439 if week else now_slot,'now_hour':anchor.hour,'range_start_slot':max(0,now_slot-hours*60+1) if hours<=12 else 0,'range_end_slot':now_slot if hours<=12 else 1439,'today':rows('SELECT '+slot+' slot,COUNT(*)*1.0/? detections FROM detections WHERE ts BETWEEN ? AND ? GROUP BY slot',(7 if week else 1,lo,hi)),'avg':rows('SELECT '+slot+' slot,COUNT(*)/7.0 avg FROM detections WHERE ts>=? AND ts<? GROUP BY slot',(prevlo,lo))}
 if action=='species':
  sci=p.get('sci','');sp=species('sci=?',(sci,));limit=max(1,min(500,int(p.get('limit',100))));offset=max(0,int(p.get('offset',0)))
  det=rows('SELECT CAST(id AS INT) detection_id,id file,substr(local,1,10) d,substr(local,12) t,confidence conf FROM detections WHERE sci=? ORDER BY ts DESC LIMIT ? OFFSET ?',(sci,limit,offset))
  return {'sci':sci,'summary':dict(sp[0],total=sp[0]['n']) if sp else None,'detections':det,'page':{'limit':limit,'offset':offset,'returned':len(det)}}
 raise ValueError('Unknown action')

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);sync()
