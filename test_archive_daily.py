import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import archive_daily as a

NOW=dt.datetime(2026,11,27,2,52,tzinfo=dt.timezone.utc)
def payload():
    return {'date':'2026-11-26','dayNumber':134,'resetsAt':'2026-11-27T05:00:00.000Z',
            'prompts':[{'id':f'p{i}','text':f'  Original question {i}?  '} for i in range(1,8)]}
def reply(data=None,status=200,ctype='application/json; charset=utf-8'):
    return status,json.dumps(data if data is not None else payload()).encode(),{'Content-Type':ctype}
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.logs=[]
    def tearDown(self):self.tmp.cleanup()
    def run_archive(self,responses):
        with patch.object(a,'request',side_effect=responses) as fetch,patch.object(a,'utcnow',return_value=NOW),patch.object(a.time,'sleep') as sleep:
            result=a.archive(self.root,log=self.logs.append)
            return result,fetch,sleep
    def seed(self,number=133,date='2026-11-25'):
        r=payload();r['dayNumber']=number;r['date']=date;r['sourceUrl']=a.SOURCE_URL
        (self.root/'history').mkdir();(self.root/'history'/f'{date}.json').write_text(json.dumps(r))
    def test_first_run_before_utc_reset_and_exact_text(self):
        self.run_archive([reply()]);r=json.loads((self.root/'latest.json').read_text())
        self.assertEqual(r['date'],'2026-11-26');self.assertEqual(r['dayNumber'],134)
        self.assertEqual(r['prompts'],payload()['prompts']);self.assertEqual(r['sourceUrl'],a.SOURCE_URL)
    def test_consecutive_and_same_dive_idempotent(self):
        self.seed();self.run_archive([reply()]);self.run_archive([reply()])
        self.assertEqual(len(list((self.root/'history').glob('*.json'))),2)
    def test_wrong_day_number_subprocess_exits_one_without_writing(self):
        self.seed();p=payload();p['dayNumber']=135
        self.rejected_subprocess(p,'dayNumber must be previous dayNumber +1')
    def test_missing_prompt_subprocess_exits_one_without_writing(self):
        self.seed();p=payload();p['prompts'].pop()
        self.rejected_subprocess(p,'prompts must contain exactly 7 entries')
    def rejected_subprocess(self,p,expected):
        before={str(f.relative_to(self.root)):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        code='import archive_daily as a,json,datetime as dt,sys\na.request=lambda:(200,'+repr(json.dumps(p).encode())+',{"Content-Type":"application/json"})\na.utcnow=lambda:dt.datetime(2026,11,27,2,52,tzinfo=dt.timezone.utc)\nsys.exit(a.main('+repr(str(self.root))+'))'
        r=subprocess.run([sys.executable,'-c',code],cwd=Path(a.__file__).parent,capture_output=True,text=True)
        self.assertEqual(r.returncode,1);self.assertIn(expected,r.stderr)
        after={str(f.relative_to(self.root)):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        self.assertEqual(before,after)
        print('INJECTION:',expected,'exit=1; archive files unchanged')
    def test_wrong_date(self):
        self.seed(date='2026-11-24')
        with self.assertRaisesRegex(ValueError,'date must be previous'):self.run_archive([reply()])
    def test_duplicate_ids_and_blank_text(self):
        for mutate in [lambda p:p['prompts'][1].update(id='p1'),lambda p:p['prompts'][0].update(text='  ')]:
            p=payload();mutate(p)
            with self.assertRaises(ValueError):self.run_archive([reply(p)])
        self.assertFalse((self.root/'latest.json').exists())
    def test_http_content_type_rejected(self):
        with self.assertRaisesRegex(ValueError,'content-type'):self.run_archive([reply(ctype='text/html')])
        self.assertFalse((self.root/'history').exists())
    def test_403_and_1010_never_retry(self):
        for status in [403,200]:
            with patch.object(a,'request',return_value=(status,b'error code: 1010',{})) as fetch,patch.object(a.time,'sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError,'被 Cloudflare 拦截'):a.archive(self.root,log=self.logs.append)
                self.assertEqual(fetch.call_count,1);sleep.assert_not_called()
        self.assertFalse((self.root/'latest.json').exists())
    def test_5xx_and_timeout_retry_once(self):
        for status in [0,500,503]:
            result,fetch,sleep=self.run_archive([(status,b'error',{}),reply()])
            self.assertEqual(result,0);self.assertEqual(fetch.call_count,2);sleep.assert_called_once_with(60)
    def test_two_5xx_do_not_write(self):
        with patch.object(a,'request',return_value=(503,b'error',{})) as fetch,patch.object(a.time,'sleep') as sleep:
            with self.assertRaises(RuntimeError):a.archive(self.root,log=self.logs.append)
            self.assertEqual(fetch.call_count,2);sleep.assert_called_once_with(60)
        self.assertFalse((self.root/'latest.json').exists())
    def test_ended_dive_retries_once(self):
        stale=payload();stale.update(date='2026-11-25',resetsAt='2026-11-26T05:00:00Z')
        _,fetch,sleep=self.run_archive([reply(stale),reply()]);self.assertEqual(fetch.call_count,2);sleep.assert_called_once_with(60)
    def test_two_stale_responses_do_not_write(self):
        stale=payload();stale.update(date='2026-11-25',resetsAt='2026-11-26T05:00:00Z')
        with self.assertRaises(a.StaleDive):self.run_archive([reply(stale),reply(stale)])
        self.assertFalse((self.root/'latest.json').exists())
    def test_no_request_headers_added(self):
        from unittest.mock import MagicMock
        r=MagicMock();r.__enter__.return_value=r;r.status=200;r.read.return_value=b'{}';r.headers={'Content-Type':'application/json'}
        with patch.object(a.urllib.request,'urlopen',return_value=r) as fetch:a.request()
        fetch.assert_called_once_with(a.SOURCE_URL,timeout=35)
if __name__=='__main__':unittest.main()
