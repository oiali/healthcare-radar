#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - build script (runs daily on GitHub Actions).

Signals ordered early -> late in the demand chain:
  Public interest (Wikipedia pageviews)  - client-side, no key, live
  Search demand (Google Trends)          - server-side via SerpApi (SERPAPI_KEY), weekly
  Prescribing by drug (OpenPrescribing)  - client-side, no key, live
  New companies by niche (Companies House) - server-side, auto-discovered from names
  Job ads by live volume (Adzuna)        - server-side

Writes dashboard.html + data.json; persists data/adzuna_history.json + data/trends.json.
"""

import os, re, json, base64, urllib.request, urllib.parse
from collections import Counter
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "healthcare-radar"}


def get_json(url, headers=None, timeout=45):
    try:
        req = urllib.request.Request(url, headers={**UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / then - 1.0) * 100.0


def add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ============================ Companies House: auto-discover niches from names
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
HEALTH_SICS = ["86900", "86220", "96020", "96040"]   # narrowed: private-clinic heavy
STOP = set(("the and of for to in a an ltd limited uk gb london clinic clinics health "
            "healthcare care medical medicine group holdings company co consulting consultancy "
            "practice practices centre center llp cic community trust nhs solutions services "
            "service management associates partners international global national services "
            "wellbeing well being ltd co uk therapy therapies treatment treatments and").split())


def ch_page(sic, dfrom, dto, start):
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies"
           f"?sic_codes={sic}&incorporated_from={dfrom}&incorporated_to={dto}"
           f"&size=100&start_index={start}")
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    return get_json(url, {"Authorization": "Basic " + auth})


def name_terms(dfrom, dto):
    cnt = Counter()
    for sic in HEALTH_SICS:
        start = 0
        for _ in range(12):                       # up to 1,200 names / SIC / window
            d = ch_page(sic, dfrom, dto, start)
            items = d.get("items") if d else None
            if not items:
                break
            for it in items:
                nm = (it.get("company_name") or "").lower()
                toks = [t for t in re.findall(r"[a-z]+", nm) if len(t) > 3 and t not in STOP]
                for t in toks:
                    cnt[t] += 1
                for i in range(len(toks) - 1):
                    cnt[toks[i] + " " + toks[i + 1]] += 1
            start += 100
            if len(items) < 100:
                break
    return cnt


def incorporations():
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    recent = name_terms(add_months(t, -3).isoformat(), t.isoformat())
    prior = name_terms(add_months(t, -15).isoformat(), add_months(t, -12).isoformat())
    rows = []
    for term, c in recent.items():
        if c < 6:                                 # min volume so it's signal not noise
            continue
        p = prior.get(term, 0)
        g12 = pct(c, p) if p > 0 else None         # None = brand-new term (flag below)
        rows.append({"name": term, "code": "new" if p == 0 else "", "latest": c,
                     "g1": None, "g3": None, "g12": g12, "accel": None, "isnew": p == 0})
    # new terms first (by volume), then by 12-mth growth
    rows.sort(key=lambda r: (r["isnew"], r["g12"] if r["g12"] is not None else 0, r["latest"]), reverse=True)
    return rows[:40]


# ============================================================ Adzuna job ads
AZ_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
AZ_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
TERMS = ["aesthetics", "dermatology", "psychiatry", "ADHD", "menopause", "endocrinology",
         "physiotherapy", "dentist", "optometrist", "audiology", "podiatry", "gynaecology",
         "urology", "cosmetic surgery", "fertility IVF", "private GP"]


def adzuna():
    if not (AZ_ID and AZ_KEY):
        return None
    rows = []
    for term in TERMS:
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/1"
               f"?app_id={AZ_ID}&app_key={AZ_KEY}&what={urllib.parse.quote(term)}"
               "&results_per_page=1&content-type=application/json")
        d = get_json(url)
        if d and "count" in d:
            rows.append({"name": term.title(), "latest": d["count"]})
    rows.sort(key=lambda x: x["latest"], reverse=True)
    return rows


# ==================================================== Google Trends (SerpApi)
SERP = os.environ.get("SERPAPI_KEY", "").strip()
TREND_Q = ["Mounjaro", "Ozempic", "Wegovy", "ADHD assessment", "menopause clinic",
           "testosterone replacement", "hair transplant", "botox", "dermal filler",
           "IV drip", "erectile dysfunction", "weight loss injection", "peptide therapy",
           "private ADHD", "HRT"]
TR_FILE = "data/trends.json"


def trends():
    if not SERP:
        return None
    try:
        cached = json.load(open(TR_FILE))
    except Exception:
        cached = None
    # only refresh weekly (Mondays) or on first run - conserves SerpApi free quota
    if cached and date.today().weekday() != 0:
        return cached.get("rows")
    rows = []
    for q in TREND_Q:
        url = ("https://serpapi.com/search.json?engine=google_trends"
               f"&q={urllib.parse.quote(q)}&geo=GB&data_type=TIMESERIES"
               "&date=today%2012-m&api_key=" + SERP)
        d = get_json(url)
        try:
            tl = d["interest_over_time"]["timeline_data"]
            v = [pt["values"][0]["extracted_value"] for pt in tl]
        except Exception:
            continue
        n = len(v)
        if n < 20:
            continue
        last = mean(v[-4:])
        rows.append({"name": q, "latest": round(last),
                     "g1": pct(last, mean(v[-8:-4])),
                     "g3": pct(last, mean(v[-17:-13])),
                     "g12": pct(last, mean(v[:4])), "accel": None})
    rows.sort(key=lambda x: (x["g12"] if x["g12"] is not None else -9e9), reverse=True)
    os.makedirs("data", exist_ok=True)
    json.dump({"rows": rows, "date": date.today().isoformat()}, open(TR_FILE, "w"), indent=1)
    return rows


# ------------------------------------------------------------------- render
def main():
    inc = incorporations() or []
    jobs = adzuna() or []
    tr = trends() or []
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    payload = json.dumps({"inc": inc, "jobs": jobs, "trends": tr}).replace("</", "<\\/")
    os.makedirs("data", exist_ok=True)
    json.dump({"updated": datetime.now(timezone.utc).isoformat(), "inc": inc, "jobs": jobs, "trends": tr},
              open("data.json", "w"), indent=2)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("{{UPDATED}}", updated).replace("{{DATA}}", payload))
    print(f"incorporations={len(inc)} jobs={len(jobs)} trends={len(tr)}")


TEMPLATE = r"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:980px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px;flex-wrap:wrap}
.tab{padding:7px 13px;font-size:13px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:14px}.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}
th.sorted{color:#1e2530}th .ar{opacity:.5;font-size:9px}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.niche{display:inline-block;font-weight:400;font-size:11.5px;color:#5b6470;background:#eef1f4;border-radius:20px;padding:1px 8px;margin-left:8px}
.newtag{background:#e6f1ff;color:#1c5fbf;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.drug{border-bottom:1px dotted #9aa4b0;cursor:help}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.accel{background:#fde7e7;color:#c23b3b;font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px}
.note{font-size:12px;color:#8b929c;margin-top:12px}.msg{color:#8b929c;font-size:13px;padding:14px 6px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:18px 0 8px}
.ov ul{margin:0 0 6px;padding-left:20px}.ov li{margin:5px 0}
.up{color:#1e7d46;font-weight:700}.dn{color:#c23b3b;font-weight:700}.big{font-size:13px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Server data updated {{UPDATED}} &middot; interest &amp; prescribing live &middot; click any % column to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="ov">Overview</div>
  <div class="tab" data-p="wk">Public interest</div>
  <div class="tab" data-p="tr">Search demand</div>
  <div class="tab" data-p="pr">Prescribing</div>
  <div class="tab" data-p="in">New companies</div>
  <div class="tab" data-p="jb">Job ads</div>
</div>
<div class="panel on ov" id="ov"><div id="ovbody" class="msg">Loading live signals&hellip;</div></div>
<div class="panel" id="wk"><div id="wkbody" class="msg">Fetching Wikipedia interest&hellip;</div></div>
<div class="panel" id="tr"><div id="trbody"></div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live prescribing&hellip;</div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="jb"><div id="jbbody"></div></div>
</div>
<script>
var RADAR = {{DATA}};
var DRUGS={
"0601023AW":["Semaglutide","Weight-loss / GLP-1","type-2 diabetes & obesity (Ozempic/Wegovy)"],
"0601023AZ":["Tirzepatide","Weight-loss / GLP-1","type-2 diabetes & obesity (Mounjaro)"],
"0601023AB":["Liraglutide","Weight-loss / GLP-1","obesity & diabetes (Saxenda/Victoza)"],
"0405010P0":["Orlistat","Weight-loss","obesity (lipase inhibitor)"],
"0405020U0":["Naltrexone-bupropion","Weight-loss","obesity (Mysimba)"],
"0404000U0":["Lisdexamfetamine","ADHD","ADHD - the adult-ADHD driver (Elvanse)"],
"0404000M0":["Methylphenidate","ADHD","ADHD stimulant"],
"0404000S0":["Atomoxetine","ADHD","ADHD (non-stimulant)"],
"0404000V0":["Guanfacine","ADHD","ADHD (non-stimulant)"],
"0604020K0":["Testosterone","Men's health / TRT","testosterone deficiency"],
"0604011Y0":["Tibolone","Menopause / HRT","menopausal symptoms"],
"0702010G0":["Estradiol (vaginal)","Menopause (GSM)","vaginal atrophy / genitourinary menopause"],
"0604020C0":["Finasteride","Hair loss / BPH","male-pattern hair loss & enlarged prostate"],
"0704050Z0":["Sildenafil","Erectile dysfunction","erectile dysfunction"],
"0407042T0":["Erenumab","Migraine (CGRP)","migraine prevention"],
"0407042R0":["Fremanezumab","Migraine (CGRP)","migraine prevention"],
"0407041AD":["Rimegepant","Migraine (gepant)","migraine treatment & prevention"],
"0407042U0":["Atogepant","Migraine (gepant)","migraine prevention"],
"0704020AE":["Mirabegron","Bladder / continence","overactive bladder"],
"0606020Z0":["Denosumab","Osteoporosis","osteoporosis (Prolia)"],
"1306010M0":["Isotretinoin","Acne / dermatology","severe acne (Roaccutane)"],
"0601023AG":["Dapagliflozin","Diabetes / SGLT2","type-2 diabetes, heart & kidney"],
"0601023AN":["Empagliflozin","Diabetes / SGLT2","type-2 diabetes, heart & kidney"],
"0403030Q0":["Sertraline","Mental health","depression & anxiety"],
"0401010AD":["Melatonin","Sleep","insomnia / sleep disorders"],
"0105030C0":["Risankizumab","Biologics (IBD / psoriasis)","Crohn's disease, psoriasis"]};
// Wikipedia article title -> niche
var WIKI={
"Tirzepatide":"Weight-loss / GLP-1","Semaglutide":"Weight-loss / GLP-1","Weight loss":"Weight-loss",
"Attention deficit hyperactivity disorder":"ADHD","Adult attention deficit hyperactivity disorder":"ADHD",
"Menopause":"Menopause / HRT","Hormone replacement therapy":"Menopause / HRT",
"Testosterone":"Men's health / TRT","Erectile dysfunction":"Sexual health",
"Migraine":"Migraine","Botulinum toxin":"Aesthetics","Dermal filler":"Aesthetics",
"Hair transplantation":"Hair restoration","Autism":"Autism","In vitro fertilisation":"Fertility",
"Ketamine":"Mental health / ketamine","Psilocybin therapy":"Psychedelics","Isotretinoin":"Acne / derm",
"Finasteride":"Hair loss","Rosacea":"Dermatology","Polycystic ovary syndrome":"Women's health",
"Perimenopause":"Menopause / HRT","Semaglutide":"Weight-loss / GLP-1","Peptide":"Peptides"};

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'&ndash;':(x>=0?'+':'')+Math.round(x)+'%';}
function num(x){return (x==null?0:x).toLocaleString('en-GB');}
function trend(r){if(r.g12==null)return'brand-new (no year-ago base)';
  var s=r.g12>=25?'rising fast':r.g12>=5?'rising':r.g12>=-5?'roughly flat':'declining';
  if(r.accel!=null&&r.accel>5&&r.g12>0)s+=' and accelerating';
  else if(r.accel!=null&&r.accel<-8&&r.g12>0)s+=' but the pace is cooling';
  return s+' (12-mth '+fmt(r.g12)+', 3-mth '+fmt(r.g3)+')';}

document.querySelectorAll('.tab').forEach(function(t){t.onclick=function(){
  document.querySelectorAll('.tab,.panel').forEach(function(e){e.classList.remove('on');});
  t.classList.add('on');document.getElementById(t.dataset.p).classList.add('on');};});

// opts: {drug:bool, noGrowth:bool, firstCol:str}
function tableRows(rows,latestLabel,opts){
  opts=opts||{};
  if(!rows||!rows.length)return '<div class="msg">No data yet.</div>';
  var cols='<th data-k="latest">'+latestLabel+'</th>';
  if(!opts.noGrowth)cols+='<th data-k="g1">1-mth</th><th data-k="g3">3-mth</th><th data-k="g12">12-mth</th>';
  var h='<table><thead><tr><th class="l">#</th><th class="l">'+(opts.firstCol||'Item')+'</th>'+cols+'<th class="l"></th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    var acc=(r.accel!=null&&r.accel>5)?'<span class="accel">accelerating</span>':(r.isnew?'<span class="newtag">new</span>':'');
    var nameCell;
    if(opts.drug){var tip=r.name+' — treats '+r.treats+'. Niche: '+r.niche+'. '+trend(r);
      nameCell='<span class="drug" title="'+tip.replace(/"/g,'&quot;')+'">'+r.name+'</span><span class="niche">'+r.niche+'</span>';}
    else if(r.niche){nameCell=r.name+'<span class="niche">'+r.niche+'</span>';}
    else{nameCell=r.name;}
    var g='';
    if(!opts.noGrowth)g='<td class="num">'+fmt(r.g1)+'</td><td class="num">'+fmt(r.g3)+'</td><td class="num g12">'+fmt(r.g12)+'</td>';
    h+='<tr data-latest="'+r.latest+'" data-g1="'+(r.g1==null?-9999:r.g1)+'" data-g3="'+(r.g3==null?-9999:r.g3)+
      '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+nameCell+
      '</td><td class="num">'+num(r.latest)+'</td>'+g+'<td class="l">'+acc+'</td></tr>';});
  return h+'</tbody></table>';
}
function wireSort(el){el.querySelectorAll('th[data-k]').forEach(function(th){th.onclick=function(){
  var tb=th.closest('table').querySelector('tbody');var k=th.dataset.k;
  th.closest('tr').querySelectorAll('th').forEach(function(x){x.classList.remove('sorted');});th.classList.add('sorted');
  Array.prototype.slice.call(tb.rows).sort(function(a,b){return (+b.dataset[k])-(+a.dataset[k]);})
    .forEach(function(r,i){r.cells[0].textContent=i+1;tb.appendChild(r);});};});}

// ---- server-baked tabs ----
document.getElementById('inbody').innerHTML=tableRows(RADAR.inc,'New (3m)',{firstCol:'Niche term'})+
  '<div class="note">Auto-discovered: the fastest-rising words/phrases in the <b>names</b> of newly-registered health companies (SICs 86900/86220/96020/96040), last 3 months vs a year ago. "new" = did not appear a year ago. Rough proxy, but it surfaces niches SIC codes bury. Click a column to sort.</div>';
document.getElementById('jbbody').innerHTML=tableRows(RADAR.jobs,'Live ads',{noGrowth:true,firstCol:'Specialty'})+
  '<div class="note">Live clinician job ads (Adzuna), ranked by current volume = where hiring demand sits now.</div>';
document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term'}):'<div class="msg">Search-demand data will appear after the next weekly run.</div>')+
  '<div class="note">Google Trends search interest in the UK (via SerpApi), refreshed weekly. Ranked by 12-month growth; click a column to sort.</div>';
document.querySelectorAll('.panel').forEach(wireSort);

// ---- Wikipedia public interest (client-side) ----
function ym(d){return d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+'0100';}
function loadWiki(){
  var now=new Date();var end=new Date(now.getFullYear(),now.getMonth(),1); // 1st of this month (exclude partial)
  var start=new Date(end.getFullYear()-2,end.getMonth(),1);
  var titles=Object.keys(WIKI);
  return Promise.all(titles.map(function(title){
    var u='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/'+
      encodeURIComponent(title.replace(/ /g,'_'))+'/monthly/'+ym(start)+'/'+ym(end);
    return fetch(u).then(function(r){return r.ok?r.json():null;}).then(function(d){
      if(!d||!d.items||d.items.length<15)return null;
      var v=d.items.map(function(x){return x.views;});var n=v.length; // last item = last complete month
      function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
      var last3=mn(n-3,n),prev3=mn(n-6,n-3),prev6=mn(n-9,n-6),year3=mn(n-15,n-12);
      var g3=pct(last3,prev3),gp=pct(prev3,prev6);
      return {name:title,niche:WIKI[title],latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:g3,
              g12:pct(last3,year3),accel:(g3!=null&&gp!=null)?g3-gp:null};
    }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}

// ---- prescribing (client-side) ----
function loadPresc(){
  return Promise.all(Object.keys(DRUGS).map(function(code){var m=DRUGS[code];
    return fetch('https://openprescribing.net/api/1.0/spending/?code='+code+'&format=json')
      .then(function(r){return r.ok?r.json():null;}).then(function(d){
        if(!d||d.length<15)return null;var v=d.map(function(x){return x.items;});var n=v.length;
        function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
        var last3=mn(n-3,n),prev3=mn(n-6,n-3),prev6=mn(n-9,n-6),year3=mn(n-15,n-12);
        var g3=pct(last3,prev3),gp=pct(prev3,prev6);if(v[n-1]<300)return null;
        return {name:m[0],niche:m[1],treats:m[2],latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:g3,
                g12:pct(last3,year3),accel:(g3!=null&&gp!=null)?g3-gp:null,date:d[n-1].date};
      }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}

function bul(r,unit){var a=(r.accel!=null&&r.accel>5)?' <span class="accel">accelerating</span>':(r.isnew?' <span class="newtag">new</span>':'');
  return '<li><b>'+r.name+'</b>'+(r.niche?' <span class="niche">'+r.niche+'</span>':'')+' '+
    (r.g12>=0?'<span class="up">':'<span class="dn">')+fmt(r.g12)+'</span> '+unit+a+'</li>';}

function overview(wiki,presc){
  var h='<div class="ov big">';
  h+='<h3>Earliest signal &mdash; public interest (Wikipedia, 12-mth)</h3><ul>';
  wiki.slice(0,4).forEach(function(r){h+=bul(r,'in pageviews');});h+='</ul>';
  if(RADAR.trends&&RADAR.trends.length){h+='<h3>Search demand (Google Trends, 12-mth)</h3><ul>';
    RADAR.trends.slice(0,4).forEach(function(r){h+=bul(r,'in search interest');});h+='</ul>';}
  h+='<h3>Prescribing by drug/niche (12-mth)</h3><ul>';
  presc.slice(0,4).forEach(function(r){h+=bul(r,'in prescription volume');});h+='</ul>';
  h+='<h3>New companies by niche (12-mth)</h3><ul>';
  (RADAR.inc||[]).slice(0,4).forEach(function(r){h+=bul(r,'in new companies');});h+='</ul>';
  var jb=(RADAR.jobs||[]).slice(0,3);
  h+='<h3>Where hiring is concentrated</h3><ul>';
  jb.forEach(function(r){h+='<li><b>'+r.name+'</b> &mdash; '+num(r.latest)+' live ads</li>';});h+='</ul>';
  h+='<div class="note">Signals ordered earliest&rarr;latest in the demand chain. Public interest &amp; prescribing fetched live in your browser; search, companies &amp; jobs refresh on the server. Not investment advice.</div></div>';
  return h;
}

var W=[],P=[];
loadWiki().then(function(w){W=w;
  document.getElementById('wkbody').innerHTML=tableRows(w,'Views / mo',{firstCol:'Topic'})+
    '<div class="note">Wikipedia pageviews per topic (last complete month), the earliest awareness signal. Fetched live in your browser. Ranked by 12-month growth; click a column to sort.</div>';
  wireSort(document.getElementById('wk'));maybeOverview();
}).catch(function(){document.getElementById('wkbody').innerHTML='<div class="msg">Could not load Wikipedia data.</div>';maybeOverview();});
loadPresc().then(function(p){P=p;
  if(!p.length){document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing.</div>';maybeOverview();return;}
  document.getElementById('prbody').innerHTML=tableRows(p,'Items / mo',{drug:true,firstCol:'Drug'})+
    '<div class="note">Individual drugs (NHS items, England), each mapped to its niche. <b>Hover a drug</b> for what it treats &amp; its trend. Latest month '+p[0].date+', live in your browser. Click a column to sort.</div>';
  wireSort(document.getElementById('pr'));maybeOverview();
}).catch(function(){document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing.</div>';maybeOverview();});

var built=false,doneCount=0;
function maybeOverview(){doneCount++;if(built)return;
  if(doneCount>=2){built=true;document.getElementById('ovbody').innerHTML=overview(W,P);}}
setTimeout(function(){if(!built){built=true;document.getElementById('ovbody').innerHTML=overview(W,P);}},9000);
</script></body></html>"""


if __name__ == "__main__":
    main()
