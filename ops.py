#!/usr/bin/env python3
"""Single-site, standard-library operations. No browser, proxy rotation or site writes."""
import tempfile
import argparse,collections,datetime as dt,json,os,re,subprocess,sys,time,urllib.request,urllib.error,urllib.parse,xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CFG=json.loads((ROOT/'config.json').read_text())
NOW=dt.datetime.now(dt.timezone.utc);DAY=NOW.date().isoformat()
LOG=ROOT/'logs'/f'{NOW:%Y%m%dT%H%M%SZ}-{os.getpid()}.jsonl'
LOG.parent.mkdir(exist_ok=True)
def save(path,obj):
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def read(path,default=None):
 p=ROOT/path;return json.loads(p.read_text()) if p.exists() else default
def http(url,payload=None):
 req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json; charset=utf-8'} if payload is not None else {})
 try:
  if urllib.parse.urlsplit(url).hostname=='krillionanswers.wiki':
   with tempfile.TemporaryDirectory() as td:
    hdr=Path(td)/'headers';out=Path(td)/'body'
    proc=subprocess.run(['curl','--silent','--show-error','--location','--max-time','35','--dump-header',str(hdr),'--output',str(out),'--write-out','%{http_code}\n%{url_effective}',url],capture_output=True,text=True)
    info=proc.stdout.splitlines();status=int(info[0]) if info else 0;final=info[1] if len(info)>1 else url
    body=out.read_bytes() if out.exists() else proc.stderr.encode()
    headers={}
    for line in hdr.read_text().splitlines() if hdr.exists() else []:
     if ':' in line:
      k,v=line.split(':',1);headers[k.strip()]=v.strip()
    if proc.returncode:status=0;body=proc.stderr.encode()
  else:
   with urllib.request.urlopen(req,timeout=35) as r:status=r.status;body=r.read();headers=dict(r.headers);final=r.url
 except urllib.error.HTTPError as e:status=e.code;body=e.read();headers=dict(e.headers);final=e.url
 except Exception as e:status=0;body=str(e).encode();headers={};final=url
 row={'time':dt.datetime.now(dt.timezone.utc).isoformat(),'method':req.get_method(),'url':url,'status':status,'finalUrl':final,'bodyFirst200':body.decode(errors='replace')[:200]}
 with LOG.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 print(json.dumps(row,ensure_ascii=False),flush=True)
 return status,body,headers,final
class SEO(HTMLParser):
 def __init__(self):super().__init__();self.title=[];self.in_title=False;self.canonical=[];self.noindex=False
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='title':self.in_title=True
  if tag=='link' and 'canonical' in a.get('rel','').lower().split():self.canonical.append(a.get('href',''))
  if tag=='meta' and (a.get('name') or '').lower() in ['robots','googlebot','bingbot']:
   if re.search(r'\b(noindex|none)\b',a.get('content',''),re.I):self.noindex=True
 def handle_endtag(self,tag):
  if tag=='title':self.in_title=False
 def handle_data(self,data):
  if self.in_title:self.title.append(data)
def same(a,b):return a.rstrip('/')==b.rstrip('/')
def sitemap():
 status,body,_,_=http(CFG['sitemap'])
 if status!=200:raise RuntimeError(f'sitemap HTTP {status}: '+body.decode(errors='replace')[:200])
 root=ET.fromstring(body);ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
 if root.tag!='{'+ns['s']+'}urlset':raise RuntimeError('Expected a urlset; inspect changed sitemap schema')
 rows={}
 for item in root.findall('s:url',ns):
  url=item.findtext('s:loc',namespaces=ns)
  if not url or urllib.parse.urlsplit(url).netloc!='krillionanswers.wiki' or not url.startswith('https://'):raise RuntimeError('Foreign or invalid sitemap URL')
  if url in rows:raise RuntimeError('Duplicate sitemap URL '+url)
  rows[url]=item.findtext('s:lastmod',default='',namespaces=ns)
 if not rows:raise RuntimeError('Empty sitemap')
 return rows
def issue(kind,body):
 title=f'[Krillion operations] {kind}'
 repo=os.environ.get('GITHUB_REPOSITORY','wutong2653-ops/krillionanswers-operations')
 # gh is authenticated locally or through GH_TOKEN in Actions; never save tokens.
 r=subprocess.run(['gh','issue','list','--repo',repo,'--state','open','--search',title+' in:title','--json','number,title'],capture_output=True,text=True)
 if r.returncode:raise RuntimeError('Issue lookup failed: '+r.stderr[:200])
 matches=[x for x in json.loads(r.stdout) if x['title']==title]
 tmp=ROOT/'logs'/'issue-body.txt';tmp.write_text(body+'\n')
 args=['gh','issue','edit',str(matches[0]['number'])] if matches else ['gh','issue','create','--title',title]
 r=subprocess.run(args+['--repo',repo,'--body-file',str(tmp)],capture_output=True,text=True)
 tmp.unlink(missing_ok=True)
 if r.returncode:raise RuntimeError('Issue write failed: '+r.stderr[:200])
 print('ISSUE',r.stdout.strip(),flush=True)
def health():
 rows=sitemap();previous=read('state/health-latest.json',{});results=[];bad=[]
 if previous and len(rows)<len(previous.get('urls',{})):bad.append('Sitemap lost URLs: '+', '.join(sorted(set(previous['urls'])-set(rows))))
 for url in rows:
  status,body,headers,final=http(url);p=SEO();p.feed(body.decode(errors='replace'))
  title=''.join(p.title).strip();canon=p.canonical
  noindex=p.noindex or bool(re.search(r'\b(noindex|none)\b',next((v for k,v in headers.items() if k.lower()=='x-robots-tag'),''),re.I))
  errors=[]
  if status!=200:errors.append(f'HTTP {status}')
  if not same(final,url):errors.append('redirected to '+final)
  if not title:errors.append('missing title')
  if len(canon)!=1 or not same(canon[0],url):errors.append('missing, duplicate or mismatching canonical')
  if noindex:errors.append('noindex')
  row={'url':url,'status':status,'title':title,'canonical':canon,'noindex':noindex,'errors':errors};results.append(row)
  if errors:bad.append(url+': '+', '.join(errors))
  time.sleep(.4)
 result={'date':DAY,'checkedAt':NOW.isoformat(),'urls':rows,'total':len(rows),'statusDistribution':dict(collections.Counter(str(r['status']) for r in results)),'added':sorted(set(rows)-set(previous.get('urls',{}))),'removed':sorted(set(previous.get('urls',{}))-set(rows)),'pages':results,'errors':bad}
 save('state/health-latest.json',result);save(f'state/health/{DAY}.json',result)
 if bad:issue('Health alert','\n'.join(bad)+'\n\nFull HTTP evidence: logs/ and state/health-latest.json');return 1
 return 0
def archive():
 from archive_daily import archive as fetch_archive
 def archive_log(message):
  print(message,flush=True)
  with LOG.open('a') as f:f.write(message+'\n')
 return fetch_archive(ROOT,log=archive_log)
def indexnow(retry=False):
 current=sitemap() if not retry else None
 old=read('state/indexnow-accepted.json',{});pending=read('state/indexnow-pending.json',{})
 if retry:
  if not pending:return 0
  if time.time()<pending['retryAt']:raise RuntimeError('Retry requested before backoff deadline')
  target=pending['snapshot'];urls=pending['urls']
 else:
  target=current;urls=sorted({u for u,v in current.items() if old.get(u)!=v}|(set(pending.get('urls',[]))&set(current)))
  if not urls:print('No new or modified URLs');return 0
 key=CFG.get('indexnowKey');location=CFG.get('indexnowKeyLocation')
 if not key or not location:raise RuntimeError('IndexNow key/keyLocation missing; site root file must already exist. No site write attempted.')
 if not re.fullmatch(r'[a-zA-Z0-9-]{8,128}',key):raise RuntimeError('Invalid IndexNow key')
 if urllib.parse.urlsplit(location).netloc!='krillionanswers.wiki' or not location.startswith('https://krillionanswers.wiki/'):raise RuntimeError('Foreign keyLocation')
 status,body,_,_=http(location)
 if status!=200 or body.decode(errors='replace').strip()!=key:raise RuntimeError('IndexNow key file invalid, HTTP '+str(status)+': '+body.decode(errors='replace')[:200])
 status,body,_,_=http(CFG['indexnowEndpoint'],{'host':'krillionanswers.wiki','key':key,'keyLocation':location,'urlList':urls})
 if status==429:
  save('state/indexnow-pending.json',{'urls':urls,'snapshot':target,'retryAt':time.time()+CFG['retrySeconds'],'attempt':2 if retry else 1,'status':429,'bodyFirst200':body.decode(errors='replace')[:200]})
  print('RATE_LIMITED; retained queue; retry after 45 minutes, no immediate retry')
  if retry:issue('IndexNow rate limit','Both attempts returned 429. Queue retained for the next daily run; not marked submitted. See logs/.')
  return 75
 if status not in (200,202):raise RuntimeError('IndexNow HTTP '+str(status)+': '+body.decode(errors='replace')[:200])
 save('state/indexnow-accepted.json',target);(ROOT/'state/indexnow-pending.json').unlink(missing_ok=True)
 save('state/indexnow-last-submit.json',{'date':DAY,'status':status,'urls':urls,'acceptedForProcessing':True});return 0
def weekly():
 files=sorted((ROOT/'state/health').glob('*.json'));items=[json.loads(p.read_text()) for p in files]
 if not items:raise RuntimeError('No health snapshots')
 latest=items[-1];cutoff=(NOW.date()-dt.timedelta(days=7)).isoformat();older=[x for x in items if x['date']<=cutoff];baseline=older[-1] if older else items[0]
 out={'date':DAY,'baselineDate':baseline['date'],'partialWeek':not bool(older),'total':latest['total'],'statusDistribution':latest['statusDistribution'],'added':sorted(set(latest['urls'])-set(baseline['urls'])),'removed':sorted(set(baseline['urls'])-set(latest['urls']))}
 save(f'state/weekly/{DAY}.json',out);issue('Weekly report',json.dumps(out,indent=2));return 0
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('task',choices=['health','indexnow','archive','weekly']);a.add_argument('--retry',action='store_true');args=a.parse_args()
 try:code=indexnow(args.retry) if args.task=='indexnow' else globals()[args.task]()
 except Exception as e:
  message=f'{args.task}: {type(e).__name__}: {e}';print(message,file=sys.stderr)
  if args.task!='archive':save('state/'+args.task+'-failure.json',{'date':DAY,'error':message,'log':str(LOG.relative_to(ROOT))})
  try:issue(args.task+' failure',message+'\n\nSee repository logs and Actions artifacts.')
  except Exception as alert_error:print('ALERT DELIVERY FAILED:',alert_error,file=sys.stderr)
  code=1
 sys.exit(code or 0)
