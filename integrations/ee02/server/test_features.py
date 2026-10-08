import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
import history,web_features
from service import atomic

class FeaturesTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
  self.old=history.DATA;history.DATA=self.data;self.addCleanup(setattr,history,'DATA',self.old)
  self.c=history.db();now=datetime.now(history.TZ)
  for i,days,sci in [(1,0,'Bird A'),(2,0,'Bird A'),(3,2,'Bird B')]:
   t=now-timedelta(days=days)
   self.c.execute('INSERT INTO detections VALUES(?,?,?,?,?,?,?,?,?,?)',(str(i),t.timestamp(),t.strftime('%Y-%m-%d %H:%M:%S'),sci,sci,.9,'https://media.birdweather.com/example.flac',0,3,'1'))
  self.c.commit();self.addCleanup(self.c.close)
 def test_windows_and_history(self):
  self.assertEqual(history.api('recent',{'hours':24})['species'][0]['n'],2)
  self.assertEqual(len(history.api('recent',{'hours':168})['species']),2)
  self.assertEqual(history.api('stats',{})['totals']['detections'],3)
  self.assertEqual(sum(x['n'] for x in history.api('hourly',{})['species'][0]['hours']),2)
  self.assertEqual(len(history.api('calendar',{})['days']),2)
 def test_upstream_stamp_decorations_and_path_boundary(self):
  import io
  class Request:
   command='GET';headers={}
   def __init__(self,path):self.path=path;self.wfile=io.BytesIO()
   def send_response(self,status):self.status=status
   def send_header(self,*args):pass
   def end_headers(self):pass
  root=self.data/'root';art=root/'avian-visitors/avian/assets/references';art.mkdir(parents=True)
  (art/'blossom.png').write_bytes(b'original-art')
  (art.parent/'private.txt').write_bytes(b'private')
  for prefix in ['/app/avian/assets/references/','/avian/assets/references/']:
   h=Request(prefix+'blossom.png');self.assertTrue(web_features.routes(h,root,self.data,atomic))
   self.assertEqual(h.status,200);self.assertEqual(h.wfile.getvalue(),b'original-art')
   head=Request(prefix+'blossom.png');head.command='HEAD'
   web_features.routes(head,root,self.data,atomic)
   self.assertEqual(head.status,200);self.assertEqual(head.wfile.getvalue(),b'')
   import hashlib
   cached=Request(prefix+'blossom.png');cached.headers={'If-None-Match':'"'+hashlib.sha256(b'original-art').hexdigest()+'"'}
   web_features.routes(cached,root,self.data,atomic)
   self.assertEqual(cached.status,304);self.assertEqual(cached.wfile.getvalue(),b'')
   (art/'blossom.png').write_bytes(b'updated-art')
   changed=Request(prefix+'blossom.png');changed.headers=cached.headers
   web_features.routes(changed,root,self.data,atomic)
   self.assertEqual(changed.status,200);self.assertEqual(changed.wfile.getvalue(),b'updated-art')
   (art/'blossom.png').write_bytes(b'original-art')
   for name in ['missing.png','../private.txt']:
    h=Request(prefix+name);web_features.routes(h,root,self.data,atomic);self.assertEqual(h.status,404)
 def test_activity_keeps_quiet_days_and_hours(self):
  series=history.api('timeseries',{'days':7})
  self.assertEqual(len(series['daily']),7)
  self.assertEqual(sum(r['detections'] for r in series['daily']),3)
  self.assertEqual(sum(r['detections']==0 for r in series['daily']),5)
  self.assertEqual([r['hour'] for r in series['by_hour']],list(range(24)))
  self.assertEqual(sum(r['detections'] for r in series['by_hour']),3)
  self.assertEqual(len(history.api('calendar',{})['days']),2)
 def test_malformed_control_is_400_and_preserves_selection(self):
  import io
  class Request:
   command='POST';path='/control'
   def __init__(self,body,length=None):
    self.headers={'Content-Length':str(len(body)) if length is None else length}
    self.rfile=io.BytesIO(body);self.wfile=io.BytesIO()
   def send_response(self,status):self.status=status
   def send_header(self,*args):pass
   def end_headers(self):pass
  atomic(self.data/'catalog.json',json.dumps([{'mode':'collage','page':0,'version':'original'}]).encode())
  web_features.select(self.data,atomic,{})
  before=(self.data/'manifest.json').read_bytes()
  for body,length in [(b'[]',None),(b'null',None),(b'{}','bad'),(b'{"action":"typo"}',None),(b'{"page":null}',None),(b'{"event":[]}',None)]:
   h=Request(body,length);web_features.routes(h,self.data,self.data,atomic)
   self.assertEqual(h.status,400);self.assertEqual((self.data/'manifest.json').read_bytes(),before)
 def test_idempotent_buttons_and_page_wrap(self):
  catalog=[{'mode':m,'page':p,'version':m+str(p)} for m,p in [('collage',0),('stamps',0),('stamps',1),('most-heard',0),('activity',0),('first-seen',0)]]
  atomic(self.data/'catalog.json',json.dumps(catalog).encode())
  a=web_features.select(self.data,atomic,{'action':'mode','event':'a'})
  self.assertEqual(a['mode'],'stamps')
  self.assertEqual(web_features.select(self.data,atomic,{'action':'mode','event':'a'})['mode'],'stamps')
  self.assertEqual(web_features.select(self.data,atomic,{'action':'previous','event':'b'})['page'],1)
  self.assertEqual(web_features.select(self.data,atomic,{'action':'next','event':'c'})['page'],0)
  before=(self.data/'manifest.json').read_bytes()
  with self.assertRaises(ValueError):web_features.select(self.data,atomic,{'mode':'invalid'})
  self.assertEqual(before,(self.data/'manifest.json').read_bytes())

if __name__=='__main__':unittest.main()
