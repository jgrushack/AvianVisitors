import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import web_features as web

class AudioCacheTest(unittest.TestCase):
 def test_evicts_oldest_and_keeps_other_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   cache=Path(tmp)
   for i,name in enumerate(('old.flac','middle.wav','new.wav')):
    p=cache/name;p.write_bytes(b'x'*10);os.utime(p,(i+1,i+1))
   (cache/'unrelated.json').write_text('keep')
   self.assertEqual(web.prune_audio(cache,20),20)
   self.assertFalse((cache/'old.flac').exists())
   self.assertTrue((cache/'middle.wav').exists())
   self.assertTrue((cache/'unrelated.json').exists())
 def test_cached_clip_does_not_redownload_evicted_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);cache=data/'audio';cache.mkdir()
   clip=cache/'123.wav';clip.write_bytes(b'wav');os.utime(clip,(1,1))
   with patch.object(web.urllib.request,'urlopen',side_effect=AssertionError('download')):
    result=web.recording_bytes(data,{'id':123},lambda *a:None)
   self.assertEqual(result,b'wav');self.assertGreater(clip.stat().st_mtime,1)
 def test_failed_conversion_still_prunes(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);cache=data/'audio';cache.mkdir();url='https://media.birdweather.com/test'
   source=cache/(web.hashlib.sha256(url.encode()).hexdigest()+'.flac');source.write_bytes(b'flac')
   with patch.object(web,'prune_audio',wraps=web.prune_audio) as prune:
    with patch.object(web.subprocess,'run',side_effect=RuntimeError('conversion failed')):
     with self.assertRaises(RuntimeError):web.recording_bytes(data,{'id':1,'audio':url,'start':0,'end':3},lambda *a:None)
    self.assertEqual(prune.call_count,2)
   self.assertEqual(list(cache.iterdir()),[source])
