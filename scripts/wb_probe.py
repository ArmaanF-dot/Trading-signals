import requests, time, collections, re
S=requests.Session(); S.headers["User-Agent"]="job-postings-research/0.1 (academic study)"
T={"gh":"airbnb pinterest robinhood coinbase lyft dropbox datadog cloudflare okta twilio toast gitlab affirm roku elastic carvana".split(),
   "lever":"palantir spotify veeva".split(),"ashby":"snowflake ramp".split()}
pat={"gh":["boards.greenhouse.io/{t}","job-boards.greenhouse.io/{t}","boards-api.greenhouse.io/v1/boards/{t}/jobs","api.greenhouse.io/v1/boards/{t}/jobs"],
     "lever":["jobs.lever.co/{t}","api.lever.co/v0/postings/{t}"],"ashby":["jobs.ashbyhq.com/{t}"]}
def cdx(u):
    for a in range(4):
        try:
            time.sleep(1.5)
            r=S.get("https://web.archive.org/cdx/search/cdx",params={"url":u,"output":"json","filter":"statuscode:200","collapse":"timestamp:6","fl":"timestamp,original,length"},timeout=90)
            if r.status_code==200: return r.json()[1:]
        except Exception as e: print("err",e)
        time.sleep(5*(a+1))
    return None
for k,ts in T.items():
    for t in ts:
        for p in pat[k]:
            u=p.format(t=t); rows=cdx(u)
            if rows is None: print(u,"FAILED"); continue
            yrs=collections.Counter(r[0][:4] for r in rows)
            print(f"{u}: {len(rows)} months  {dict(sorted(yrs.items()))}",flush=True)
# parse check on one greenhouse html snapshot and one api snapshot
for u in ["boards.greenhouse.io/airbnb","boards-api.greenhouse.io/v1/boards/airbnb/jobs","jobs.lever.co/palantir"]:
    rows=cdx(u)
    if rows:
        ts=rows[len(rows)//2][0]
        r=S.get(f"https://web.archive.org/web/{ts}id_/https://{u}",timeout=90)
        txt=r.text
        print("SAMPLE",u,ts,r.status_code,len(txt),"openings:",txt.count('class="opening"'),"total:",re.findall(r'"total":\s*(\d+)',txt)[:1],"postings:",txt.count('class="posting"'))
