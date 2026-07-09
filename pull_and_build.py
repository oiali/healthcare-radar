#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - build script (runs daily on GitHub Actions).

Split by where the data can actually be fetched:

  Server-side (needs secret API keys, so fetched here and baked into the page):
    - New incorporations by health SIC   (Companies House, CH_API_KEY)
    - Clinician job ads, ranked by live volume (Adzuna, ADZUNA_APP_ID/KEY)

  Client-side (done in the visitor's browser - see the page <script>):
    - NHS prescribing growth (OpenPrescribing). Their Cloudflare 403s datacentre
      IPs (so a cloud job can't fetch it) but allows real browsers + CORS, so the
      page fetches it live when opened. Always current, no cloud dependency.
    - Overview / key takeaways (combines all three sources).

Writes dashboard.html + data.json; accumulates data/adzuna_history.json.
"""

import os, json, base64, urllib.request, urllib.parse
from datetime import datetime, timezone, date
from statistics import mean

UA = {"User-Agent": "healthcare-radar"}


def get_json(url, headers=None, timeout=30):
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


# ------------------------------------------------------- Companies House
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
SIC = {
    "86101": "Hospital activities", "86102": "Medical nursing home", "86210": "General practice",
    "86220": "Specialist medical practice", "86230": "Dental practice", "86900": "Other human health",
    "96020": "Hairdressing & beauty", "96040": "Physical well-being",
    "87100": "Residential nursing care", "87300": "Residential care (elderly/disabled)",
    "88100": "Social work (elderly/disabled)", "88990": "Other social work",
}


def ch_hits(sic, dfrom, dto):
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies"
           f"?sic_codes={sic}&incorporated_from={dfrom}&incorporated_to={dto}&size=1")
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    d = get_json(url, {"Authorization": "Basic " + auth})
    return d.get("hits") if d else None


def incorporations():
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    def r(a, b): return add_months(t, a).isoformat(), add_months(t, b).isoformat()
    rows = []
    for sic, name in SIC.items():
        now3 = ch_hits(sic, *r(-3, 0)); prev3 = ch_hits(sic, *r(-6, -3))
        prev6 = ch_hits(sic, *r(-9, -6)); year3 = ch_hits(sic, *r(-15, -12))
        if now3 is None:
            continue
        g3 = pct(now3, prev3)
        accel = (g3 - pct(prev3, prev6)) if (g3 is not None and pct(prev3, prev6) is not None) else None
        rows.append({"name": name, "code": sic, "latest": now3, "g1": None,
                     "g3": g3, "g12": pct(now3, year3), "accel": accel})
    rows.sort(key=lambda x: (x["g12"] if x["g12"] is not None else -9e9), reverse=True)
    return rows


# ------------------------------------------------------------- Adzuna
AZ_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
AZ_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
TERMS = ["aesthetics", "dermatology", "psychiatry", "ADHD", "menopause", "endocrinology",
         "physiotherapy", "dentist", "optometrist", "audiology", "podiatry", "gynaecology",
         "urology", "cosmetic surgery", "fertility IVF", "private GP"]
HIST = "data/adzuna_history.json"


def adzuna():
    if not (AZ_ID and AZ_KEY):
        return None
    os.makedirs("data", exist_ok=True)
    try:
        hist = json.load(open(HIST))
    except Exception:
        hist = {}
    today = date.today().isoformat()
    for term in TERMS:
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/1"
               f"?app_id={AZ_ID}&app_key={AZ_KEY}&what={urllib.parse.quote(term)}"
               "&results_per_page=1&content-type=application/json")
        d = get_json(url)
        if not d or "count" not in d:
            continue
        hist.setdefault(term, [])
        hist[term] = [h for h in hist[term] if h[0] != today] + [[today, d["count"]]]
        hist[term].sort()
    json.dump(hist, open(HIST, "w"), indent=1)

    rows = []
    for term, series in hist.items():
        if not series:
            continue
        latest = series[-1][1]
        def ago(days):
            from datetime import timedelta
            tgt = (date.today() - timedelta(days=days)).isoformat()
            cand = [c for dt, c in series if dt <= tgt]
            return cand[-1] if cand else None
        rows.append({"name": term.title(), "code": "", "latest": latest,
                     "g1": pct(latest, ago(7)), "g3": pct(latest, ago(30)),
                     "g12": pct(latest, ago(90)), "accel": None})
    rows.sort(key=lambda x: x["latest"], reverse=True)   # rank by live volume
    return rows


# ------------------------------------------------------------- render
def main():
    inc = incorporations() or []
    jobs = adzuna() or []
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    payload = json.dumps({"inc": inc, "jobs": jobs}).replace("</", "<\\/")

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "inc": inc, "jobs": jobs}, f, indent=2)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("{{UPDATED}}", updated).replace("{{DATA}}", payload))
    print(f"incorporations={len(inc)} jobs={len(jobs)}")


TEMPLATE = r"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:940px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px;flex-wrap:wrap}
.tab{padding:7px 14px;font-size:13.5px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:14px 14px}
.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.code{color:#aab0b8;font-weight:400;font-size:12px;margin-left:8px}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.accel{background:#fde7e7;color:#c23b3b;font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px}
.note{font-size:12px;color:#8b929c;margin-top:12px}
.msg{color:#8b929c;font-size:13px;padding:14px 6px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:2px 0 8px}
.ov h3{margin-top:18px}
.ov ul{margin:0 0 6px;padding-left:20px}.ov li{margin:5px 0}
.up{color:#1e7d46;font-weight:700}.dn{color:#c23b3b;font-weight:700}
.big{font-size:13px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Incorporations &amp; jobs updated {{UPDATED}} &middot; prescribing live</span></div>
<div class="tabs">
  <div class="tab on" data-p="ov">Overview</div>
  <div class="tab" data-p="pr">Prescribing</div>
  <div class="tab" data-p="in">New incorporations</div>
  <div class="tab" data-p="jb">Job ads</div>
</div>
<div class="panel on ov" id="ov"><div id="ovbody" class="msg">Loading live signals&hellip;</div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live NHS prescribing data&hellip;</div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="jb"><div id="jbbody"></div></div>
<div class="note" id="foot"></div>
</div>
<script>
var RADAR = {{DATA}};
var SECTIONS = {"0101":"Dyspepsia & reflux","0106":"Laxatives","0204":"Beta-blockers","0205":"Hypertension & heart failure","0206":"Nitrates & calcium blockers","0208":"Anticoagulants","0212":"Lipid-regulating","0301":"Bronchodilators","0302":"Respiratory corticosteroids","0304":"Antihistamines & allergy","0401":"Hypnotics & anxiolytics","0402":"Antipsychotics","0403":"Antidepressants","0404":"CNS stimulants & ADHD","0406":"Nausea & vertigo","0407":"Analgesics","0408":"Antiepileptics","0409":"Parkinson's","0410":"Substance dependence","0411":"Dementia","0501":"Antibacterials","0503":"Antivirals","0601":"Diabetes","0602":"Thyroid","0603":"Endocrine corticosteroids","0604":"Sex hormones (HRT, testosterone)","0606":"Metabolic bone / bisphosphonates","0607":"Other endocrine","0701":"Obstetrics & gynaecology","0703":"Contraceptives","0704":"Bladder, urinary & ED","0801":"Cytotoxics","0802":"Immunomodulators & biologics","0901":"Anaemia & blood","1001":"Rheumatic disease & NSAIDs","1106":"Glaucoma","1203":"Oropharynx","1301":"Emollients & barrier","1305":"Psoriasis & eczema","1306":"Acne","1404":"Vaccines"};

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'&ndash;':(x>=0?'+':'')+Math.round(x)+'%';}
function num(x){return x.toLocaleString('en-GB');}

// tab switching + column sort
document.querySelectorAll('.tab').forEach(function(t){t.onclick=function(){
  document.querySelectorAll('.tab,.panel').forEach(function(e){e.classList.remove('on');});
  t.classList.add('on');document.getElementById(t.dataset.p).classList.add('on');};});

function table(rows, latestLabel){
  if(!rows||!rows.length) return '<div class="msg">No data.</div>';
  var h='<table><thead><tr><th class="l">#</th><th class="l">Area</th>'+
    '<th data-k="latest">'+latestLabel+'</th><th data-k="g1">1-mth</th>'+
    '<th data-k="g3">3-mth</th><th data-k="g12">12-mth</th><th class="l"></th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    var acc=(r.accel!=null&&r.accel>5)?'<span class="accel">accelerating</span>':'';
    var code=r.code?'<span class="code">'+r.code+'</span>':'';
    h+='<tr data-latest="'+r.latest+'" data-g1="'+(r.g1==null?-9999:r.g1)+'" data-g3="'+(r.g3==null?-9999:r.g3)+
      '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.name+code+
      '</td><td class="num">'+num(r.latest)+'</td><td class="num">'+fmt(r.g1)+'</td><td class="num">'+
      fmt(r.g3)+'</td><td class="num g12">'+fmt(r.g12)+'</td><td class="l">'+acc+'</td></tr>';
  });
  return h+'</tbody></table>';
}
function wireSort(el){
  el.querySelectorAll('th[data-k]').forEach(function(th){th.onclick=function(){
    var tb=th.closest('table').querySelector('tbody');var k=th.dataset.k;
    Array.prototype.slice.call(tb.rows).sort(function(a,b){return (+b.dataset[k])-(+a.dataset[k]);})
      .forEach(function(r,i){r.cells[0].textContent=i+1;tb.appendChild(r);});};});
}

// render server-side tabs
document.getElementById('inbody').innerHTML =
  table(RADAR.inc,'New (3m)') + '<div class="note">New company registrations by health SIC code (Companies House). Ranked by 12-month growth in new incorporations; "accelerating" = the 3-month rate is rising vs the prior 3 months.</div>';
document.getElementById('jbbody').innerHTML =
  table(RADAR.jobs,'Live ads') + '<div class="note">Live clinician job ads (Adzuna), <b>ranked by current volume</b> - i.e. where hiring demand is concentrated right now. The 1/3/12-month growth fills in from daily snapshots (Adzuna has no historical feed), so the first movements appear within days.</div>';
document.querySelectorAll('.panel').forEach(wireSort);

// prescribing: fetched live from the visitor's browser
function loadPrescribing(){
  var entries=Object.keys(SECTIONS).map(function(c){return [c,SECTIONS[c]];});
  return Promise.all(entries.map(function(pair){
    var code=pair[0],name=pair[1];
    return fetch('https://openprescribing.net/api/1.0/spending/?code='+code+'&format=json')
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(!d||!d.length||d.length<15) return null;
        var v=d.map(function(x){return x.items;});var n=v.length;
        function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
        var last3=mn(n-3,n),prev3=mn(n-6,n-3),prev6=mn(n-9,n-6),year3=mn(n-15,n-12);
        var g3=pct(last3,prev3),gp=pct(prev3,prev6);
        if(v[n-1]<2000) return null;
        return {code:code,name:name,latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:g3,
                g12:pct(last3,year3),accel:(g3!=null&&gp!=null)?g3-gp:null,date:d[n-1].date};
      }).catch(function(){return null;});
  })).then(function(res){
    return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});
  });
}

function bullet(r,unit){var a=(r.accel!=null&&r.accel>5)?' <span class="accel">accelerating</span>':'';
  return '<li><b>'+r.name+'</b> '+(r.g12>=0?'<span class="up">':'<span class="dn">')+fmt(r.g12)+'</span> '+unit+a+'</li>';}

function buildOverview(presc){
  var h='<div class="ov big">';
  h+='<h3>Fastest-rising demand &mdash; NHS prescribing (12-mth)</h3><ul>';
  presc.slice(0,4).forEach(function(r){h+=bullet(r,'in prescription volume');});
  h+='</ul>';
  var inc=(RADAR.inc||[]).slice().filter(function(r){return r.g12!=null;}).slice(0,3);
  h+='<h3>Fastest-rising supply &mdash; new company formation (12-mth)</h3><ul>';
  inc.forEach(function(r){h+=bullet(r,'in new incorporations');});
  h+='</ul>';
  var jb=(RADAR.jobs||[]).slice(0,3);
  h+='<h3>Where hiring is concentrated &mdash; live clinician job ads</h3><ul>';
  jb.forEach(function(r){h+='<li><b>'+r.name+'</b> &mdash; '+num(r.latest)+' live ads</li>';});
  h+='</ul>';
  var accel=presc.filter(function(r){return r.accel!=null&&r.accel>5;}).slice(0,3);
  if(accel.length){h+='<h3>Watch &mdash; accelerating (rate of growth itself rising)</h3><ul>';
    accel.forEach(function(r){h+='<li><b>'+r.name+'</b> &mdash; 3-mth growth jumped to '+fmt(r.g3)+'</li>';});h+='</ul>';}
  h+='<div class="note">Overview auto-built from the three sources below. Prescribing is fetched live from OpenPrescribing when you open this page; incorporations &amp; job ads refresh daily. Not investment advice.</div></div>';
  return h;
}

loadPrescribing().then(function(rows){
  if(!rows.length){
    document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing data (your browser/network blocked the request to OpenPrescribing).</div>';
    document.getElementById('ovbody').innerHTML=buildOverview([]);
    document.querySelector('#pr').querySelectorAll('th[data-k]').forEach(function(){});
    return;
  }
  var pd=rows[0].date;
  document.getElementById('prbody').innerHTML=
    table(rows,'Items / mo')+'<div class="note">NHS items dispensed in England (OpenPrescribing), whole-BNF scan, latest month '+pd+'. Fetched live in your browser. Ranked by 12-month growth; click any column to re-sort.</div>';
  wireSort(document.getElementById('pr'));
  document.getElementById('ovbody').innerHTML=buildOverview(rows);
}).catch(function(){
  document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing data.</div>';
  document.getElementById('ovbody').innerHTML=buildOverview([]);
});
</script></body></html>"""


if __name__ == "__main__":
    main()
