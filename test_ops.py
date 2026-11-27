import unittest,tempfile,json,time,datetime as dt,io,urllib.error
from unittest.mock import MagicMock
from pathlib import Path
from unittest.mock import patch
import ops
class OperationsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.orig=ops.ROOT;self.cfg=ops.CFG.copy();ops.ROOT=self.root;ops.CFG.update(indexnowKey='a'*32,indexnowKeyLocation=ops.CFG['site']+'/'+'a'*32+'.txt');self.url=ops.CFG['site']+'/answers'
 def tearDown(self):ops.ROOT=self.orig;ops.CFG=self.cfg;self.temp.cleanup()
 def test_rate_limit_preserves_unaccepted_queue(self):
  with patch.object(ops,'sitemap',return_value={self.url:'2026-11-24'}),patch.object(ops,'http',side_effect=[(200,b'a'*32,{},''),(429,b'too many requests',{},'')]):
   self.assertEqual(ops.indexnow(),75)
  self.assertFalse((self.root/'state/indexnow-accepted.json').exists());q=ops.read('state/indexnow-pending.json');self.assertEqual(q['urls'],[self.url]);self.assertGreater(q['retryAt'],time.time()+2600)
 def test_success_only_sends_changed_urls(self):
  old=self.url+'/old';ops.save('state/indexnow-accepted.json',{old:'unchanged',self.url:'old'})
  with patch.object(ops,'sitemap',return_value={old:'unchanged',self.url:'new'}),patch.object(ops,'http',side_effect=[(200,b'a'*32,{},''),(202,b'',{},'')]) as h:
   self.assertEqual(ops.indexnow(),0);self.assertEqual(h.call_args[0][1]['urlList'],[self.url])
  self.assertEqual(ops.read('state/indexnow-accepted.json')[self.url],'new')
 def test_second_429_alerts_and_retains_queue(self):
  ops.save('state/indexnow-pending.json',{'snapshot':{self.url:'x'},'urls':[self.url],'retryAt':0})
  with patch.object(ops,'http',side_effect=[(200,b'a'*32,{},''),(429,b'rate limited',{},'')]),patch.object(ops,'issue') as issue:
   self.assertEqual(ops.indexnow(True),75);issue.assert_called_once()
  self.assertEqual(ops.read('state/indexnow-pending.json')['attempt'],2)
 def test_malformed_key_file_never_submits(self):
  with patch.object(ops,'sitemap',return_value={self.url:'x'}),patch.object(ops,'http',return_value=(404,b'not found',{},'')) as h:
   with self.assertRaises(RuntimeError):ops.indexnow()
   self.assertEqual(h.call_count,1)
 def test_health_detects_noindex_and_wrong_canonical(self):
  html=b'<title>Present</title><link rel="canonical" href="https://wrong.example/"><meta name="robots" content="none">'
  with patch.object(ops,'sitemap',return_value={self.url:'x'}),patch.object(ops,'http',return_value=(200,html,{},self.url)),patch.object(ops.time,'sleep'),patch.object(ops,'issue') as issue:
   self.assertEqual(ops.health(),1);issue.assert_called_once()
  r=ops.read('state/health-latest.json');self.assertTrue(r['pages'][0]['noindex']);self.assertEqual(len(r['errors']),1)
 def test_http_records_403_and_body_without_retry(self):
  oldlog=ops.LOG;ops.LOG=self.root/'receipt.jsonl'
  try:
   err=urllib.error.HTTPError('https://krillion.io/api/today',403,'Forbidden',{},io.BytesIO(b'error code: 1010'))
   with patch.object(ops.urllib.request,'urlopen',side_effect=err) as net:
    status,body,_,_=ops.http('https://krillion.io/api/today')
    self.assertEqual(status,403);self.assertEqual(body,b'error code: 1010');self.assertEqual(net.call_count,1)
   receipt=json.loads(ops.LOG.read_text());self.assertEqual(receipt['method'],'GET');self.assertEqual(receipt['status'],403);self.assertEqual(receipt['bodyFirst200'],'error code: 1010')
  finally:ops.LOG=oldlog
 def test_http_success_records_post_method(self):
  oldlog=ops.LOG;ops.LOG=self.root/'receipt.jsonl'
  try:
   response=MagicMock();response.status=202;response.read.return_value=b'';response.headers={};response.url='https://api.indexnow.org/indexnow'
   response.__enter__.return_value=response
   with patch.object(ops.urllib.request,'urlopen',return_value=response):
    self.assertEqual(ops.http(response.url,{'host':'krillionanswers.wiki'})[0],202)
   self.assertEqual(json.loads(ops.LOG.read_text())['method'],'POST')
  finally:ops.LOG=oldlog
if __name__=='__main__':unittest.main()
