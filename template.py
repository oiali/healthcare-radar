"""HTML template for the radar dashboard. Kept separate: the file tools truncate above ~30KB."""

TEMPLATE = r"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:1180px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px;flex-wrap:wrap}
.tab{padding:7px 12px;font-size:13px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.tab .t{font-size:10px;color:#aab0b8;font-weight:700;margin-right:5px}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:14px}.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 9px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}th.sorted{color:#1e2530}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.niche{display:inline-block;font-weight:400;font-size:11.5px;color:#5b6470;background:#eef1f4;border-radius:20px;padding:1px 8px;margin-left:8px}
.newtag{background:#e6f1ff;color:#1c5fbf;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.found{background:#eafaf1;color:#1e7d46;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.drug{border-bottom:1px dotted #9aa4b0;cursor:help}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.note{font-size:12px;color:#8b929c;margin-top:12px}.msg{color:#8b929c;font-size:13px;padding:14px 6px}
.up{color:#1e7d46;font-weight:700}.dn{color:#c23b3b}.na{color:#c9ced4}
.nap{color:#c9ced4;font-size:11px;font-style:italic}
.st{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;white-space:nowrap}
.s1{background:#eef1f4;color:#5b6470}.s2{background:#e6f1ff;color:#1c5fbf}
.s3{background:#eafaf1;color:#1e7d46}.s4{background:#fdf1e3;color:#a76a1e}
.s0{background:#fde7e7;color:#c23b3b}
.iv{font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px;white-space:nowrap}
.iv-go{background:#eafaf1;color:#1e7d46}.iv-mid{background:#fdf1e3;color:#a76a1e}
.iv-no{background:#fde7e7;color:#c23b3b}.iv-na{background:#f1f2f4;color:#9aa0a8}
.mv{background:#f7fbff;border:1px solid #dce9f7;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:13.5px}
.mv b{color:#1c5fbf}.mv ul{margin:6px 0 0;padding-left:20px}.mv li{margin:3px 0}
.chain{font-size:12.5px;color:#6b7280;background:#f7f8f9;border-left:3px solid #d8dce1;padding:9px 12px;margin-bottom:14px}
.warn{font-size:12.5px;color:#8a6d3b;background:#fff8ec;border-left:3px solid #e8c886;padding:9px 12px;margin-bottom:14px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Server data {{UPDATED}} &middot; prescribing live in your browser &middot; click any column to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="st">The Stack</div>
  <div class="tab" data-p="wt"><span class="t">T0</span>NHS waits</div>
  <div class="tab" data-p="tr"><span class="t">T1</span>Search</div>
  <div class="tab" data-p="in"><span class="t">T2</span>New companies</div>
  <div class="tab" data-p="ae"><span class="t">T2</span>Aesthetics</div>
  <div class="tab" data-p="cq"><span class="t">T3</span>New clinics</div>
  <div class="tab" data-p="jb"><span class="t">T3</span>Job ads</div>
  <div class="tab" data-p="pr"><span class="t">T4</span>Prescribing</div>
  <div class="tab" data-p="iv">Investability</div>
</div>
<div class="panel on" id="st"><div id="stbody" class="msg">Building the stack&hellip;</div></div>
<div class="panel" id="wt"><div id="wtbody"></div></div>
<div class="panel" id="tr"><div id="trbody"></div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="ae"><div id="aebody"></div></div>
<div class="panel" id="cq"><div id="cqbody"></div></div>
<div class="panel" id="jb"><div id="jbbody"></div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live prescribing&hellip;</div></div>
<div class="panel" id="iv"><div id="ivbody"></div></div>
</div>
<script>
var RADAR = {{DATA}};
var DRUGQ = RADAR.drugq||{};          // niche -> comma-separated BNF codes (batched: 16 calls, not 76)
var DRUGS = RADAR.drugs||{};          // code -> [name, niche, treats]
var NOPRESC = RADAR.nopresc||[];      // niches with NO valid NHS prescribing proxy -> show n/a, not a dash
var RISING = 10;

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'<span class="na">&ndash;</span>':(x>=0?'+':'')+Math.round(x)+'%';}
function cell(x,na){if(x==null)return na?'<span class="nap">n/a</span>':'<span class="na">&ndash;</span>';
  return '<span class="'+(x>=RISING?'up':(x<=-RISING?'dn':''))+'">'+(x>=0?'+':'')+Math.round(x)+'%</span>';}
function num(x){return (x==null?0:x).toLocaleString('en-GB');}

document.querySelectorAll('.tab').forEach(function(t){t.onclick=function(){
  document.querySelectorAll('.tab,.panel').forEach(function(e){e.classList.remove('on');});
  t.classList.add('on');document.getElementById(t.dataset.p).classList.add('on');};});

function tableRows(rows,latestLabel,opts){
  opts=opts||{};
  if(!rows||!rows.length)return '<div class="msg">No data yet.</div>';
  var h='<table><thead><tr><th class="l">#</th><th class="l">'+(opts.firstCol||'Item')+'</th>'+
    '<th data-k="latest">'+latestLabel+'</th><th data-k="g1">1-mth</th><th data-k="g3">3-mth</th>'+
    '<th data-k="g12">12-mth</th><th class="l"></th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    var tag=r.isnew?'<span class="newtag">new</span>':(r.found?'<span class="found">auto-found</span>':'');
    var nm=r.name;
    if(opts.drug&&r.treats)nm='<span class="drug" title="'+String(r.treats).replace(/"/g,'&quot;')+'">'+r.name+'</span>';
    if(r.niche)nm+='<span class="niche">'+r.niche+'</span>';
    h+='<tr data-latest="'+(r.latest||0)+'" data-g1="'+(r.g1==null?-9999:r.g1)+'" data-g3="'+(r.g3==null?-9999:r.g3)+
      '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+nm+
      '</td><td class="num">'+num(r.latest)+'</td><td class="num">'+fmt(r.g1)+'</td><td class="num">'+
      fmt(r.g3)+'</td><td class="num g12">'+fmt(r.g12)+'</td><td class="l">'+tag+'</td></tr>';});
  return h+'</tbody></table>';
}
function wireSort(el){el.querySelectorAll('th[data-k]').forEach(function(th){th.onclick=function(){
  var tb=th.closest('table').querySelector('tbody');var k=th.dataset.k;
  th.closest('tr').querySelectorAll('th').forEach(function(x){x.classList.remove('sorted');});th.classList.add('sorted');
  Array.prototype.slice.call(tb.rows).sort(function(a,b){return (+b.dataset[k])-(+a.dataset[k]);})
    .forEach(function(r,i){r.cells[0].textContent=i+1;tb.appendChild(r);});};});}

function agg(rows){
  var m={};(rows||[]).forEach(function(r){
    if(!r.niche||r.g12==null)return;
    var w=Math.max(r.latest||1,1);
    if(!m[r.niche])m[r.niche]={w:0,s:0};
    m[r.niche].w+=w;m[r.niche].s+=w*r.g12;});
  var o={};for(var k in m)o[k]=m[k].s/m[k].w;return o;
}
function stage(t1,t2,t3,t4,na4){
  var up=function(x){return x!=null&&x>=RISING;};
  var n=[t1,t2,t3,t4].filter(up).length;
  if(n===0)return ['s1','&mdash;',0];
  if(up(t4)&&!up(t1)&&!up(t2))return ['s0','Late · demand already served',n];
  if(up(t1)&&!up(t2)&&!up(t3)&&!up(t4))return ['s1','1 · Intent only — speculative',n];
  if(up(t1)&&up(t2)&&!up(t3)&&!up(t4))return ['s2','2 · Entry — founders moving',n];
  if(up(t3)&&!up(t4))return ['s3','3 · Build-out — capacity arriving',n];
  if(up(t4)&&n>=3)return ['s4','4 · Mainstream — likely priced in',n];
  return ['s2','Mixed',n];
}
function ivBadge(v){
  if(!v)return '<span class="iv iv-na">no data</span>';
  var s=v.verdict||'';var c='iv-mid';
  if(/too small|already consolidated/i.test(s))c='iv-no';
  else if(/fragmented|runway/i.test(s))c='iv-go';
  var tip=(v.providers!=null?v.providers+' providers, '+v.locations+' locations, '+
    (v.single_site_pct!=null?Math.round(v.single_site_pct)+'% single-site':''):'');
  return '<span class="iv '+c+'" title="'+tip.replace(/"/g,'&quot;')+'">'+s+'</span>';
}
function buildStack(presc){
  var T0=agg(RADAR.waits),T1=agg(RADAR.trends),
      T2=agg((RADAR.inc||[]).concat(RADAR.aes||[])),
      T3=agg(RADAR.cqc),T4=agg(presc);
  var IV=RADAR.invest||{};
  var names={};[T0,T1,T2,T3,T4].forEach(function(o){for(var k in o)names[k]=1;});
  for(var k in IV)names[k]=1;
  var rows=Object.keys(names).map(function(n){
    var na4=NOPRESC.indexOf(n)>=0;
    var s=stage(T1[n],T2[n],T3[n],T4[n],na4);
    return {n:n,t0:T0[n],t1:T1[n],t2:T2[n],t3:T3[n],t4:T4[n],na4:na4,
            cls:s[0],label:s[1],conv:s[2],iv:IV[n]};});
  rows.sort(function(x,y){
    if(y.conv!==x.conv)return y.conv-x.conv;
    return (y.t1==null?-9e9:y.t1)-(x.t1==null?-9e9:x.t1);});

  var h='<div class="chain"><b>Read left to right.</b> A niche is worth acting on when the <b>early</b> tiers are lit, the <b>late</b> ones are not, and it is <b>investable</b>. Once T4 is rising, the demand is already being served.<br>'+
    '<b>T0 NHS waits</b> (the causal driver) → <b>T1 Search</b> (weeks) → <b>T2 New companies</b> (months) → <b>T3 New clinics</b> (6–18 mth) → <b>T4 NHS prescribing</b> (12+ mth). '+
    '<b>Investability</b> is a stock, not a flow: how many independent operators exist to buy.</div>';

  h+='<div class="warn"><b>Before you trust a cell:</b> the +10% "firing" line and the tier ordering are <b>not yet backtested</b> — they are reasoning, not evidence. T3 counts are small (5–20 per niche), so a big % on a thin base is noise. T4 shows <i>n/a</i>, not a dash, where no NHS drug proxy exists (aesthetics, diagnostics, dental, tongue-tie, longevity, MSK, audiology, eye, private GP) — read it as "not applicable", never "not yet".</div>';

  if(RADAR.moved&&RADAR.moved.length){
    h+='<div class="mv"><b>What moved in the last 7 days</b><ul>';
    RADAR.moved.forEach(function(m){
      h+='<li>'+m.niche+' — now firing on <b>'+m.to+'</b> of the 3 early tiers (was '+m.from+' on '+m.since+')</li>';});
    h+='</ul></div>';
  }

  h+='<table><thead><tr><th class="l">#</th><th class="l">Niche</th>'+
     '<th data-k="t0">T0 NHS wait</th><th data-k="t1">T1 Search</th><th data-k="t2">T2 Companies</th>'+
     '<th data-k="t3">T3 Clinics</th><th data-k="t4">T4 Prescribing</th>'+
     '<th data-k="conv">Tiers</th><th class="l">Stage</th><th class="l">Investability</th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    h+='<tr data-t0="'+(r.t0==null?-9999:r.t0)+'" data-t1="'+(r.t1==null?-9999:r.t1)+'" data-t2="'+(r.t2==null?-9999:r.t2)+
       '" data-t3="'+(r.t3==null?-9999:r.t3)+'" data-t4="'+(r.t4==null?-9999:r.t4)+
       '" data-conv="'+r.conv+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.n+'</td>'+
       '<td class="num">'+cell(r.t0)+'</td><td class="num">'+cell(r.t1)+'</td><td class="num">'+cell(r.t2)+'</td>'+
       '<td class="num">'+cell(r.t3)+'</td><td class="num">'+cell(r.t4,r.na4)+'</td>'+
       '<td class="num">'+r.conv+'/4</td><td class="l"><span class="st '+r.cls+'">'+r.label+'</span></td>'+
       '<td class="l">'+ivBadge(r.iv)+'</td></tr>';});
  h+='</tbody></table><div class="note">All figures are <b>12-month growth</b>, volume-weighted across every item mapped to that niche. A dash = the source has no reading (absent, not zero). '+
     '<b>Ordering caveat:</b> the chain is the default for a <i>demand-led</i> niche. For a <i>drug-led</i> one (GLP-1) T4 moves early — a new molecule creates demand rather than following it. '+
     'T0 (NHS waits) covers consultant-led elective care only, so it is structurally blind to weight-loss and ADHD.</div>';
  return h;
}

document.getElementById('wtbody').innerHTML=(RADAR.waits&&RADAR.waits.length?
  tableRows(RADAR.waits,'Waiting',{firstCol:'NHS specialty'}):'<div class="msg">NHS RTT data unavailable this run.</div>')+
  '<div class="note"><b>T0 · the causal driver.</b> NHS England Referral-to-Treatment waits. Growth is measured on the <b>count waiting over 18 weeks</b> — deterioration in NHS access — not on total volume. When the NHS stops coping, patients go private; everything else on this dashboard is downstream of this. <b>Limits:</b> England only, ~6 weeks in arrears, consultant-led elective care only — so it is <b>blind to weight-loss and ADHD</b>, the two biggest private-pay niches. g1 is noisy (non-submitting trusts create fake swings); trust g3/g12.</div>';

document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term'}):'<div class="msg">Search data appears after the next weekly run.</div>')+
  '<div class="note"><b>T1 · earliest demand signal.</b> UK Google search interest (SerpApi), weekly. Terms tagged <span class="found">auto-found</span> were <b>discovered</b> by the supply-side tiers and fed back in automatically — so this can surface niches nobody pre-listed. Note it is a 0–100 <i>relative</i> index over a 12-month window: it cannot see a multi-year build-up.</div>';

document.getElementById('inbody').innerHTML=tableRows(RADAR.inc,'New (3m)',{firstCol:'Niche term'})+
  '<div class="note"><b>T2 · months.</b> Words rising fastest in the <b>names</b> of newly-incorporated health companies (9 SIC codes incl. 86210 general medical practice, where the ADHD/menopause/GLP-1 telehealth operators register). Incorporating is the cheapest possible bet on a niche, which is why it moves early. Blank growth = year-ago base under 3.</div>';

document.getElementById('aebody').innerHTML=(RADAR.aes&&RADAR.aes.length?
  tableRows(RADAR.aes,'New (12m)',{firstCol:'Aesthetics keyword'}):'<div class="msg">Aesthetics miner returned nothing this run.</div>')+
  '<div class="note"><b>T2 · the CQC blind spot, closed.</b> Purely cosmetic treatment is <b>not</b> a CQC "regulated activity" — DHSC: <i>"TDDI does not include interventions carried out purely for cosmetic purposes."</i> So a botox/filler clinic needs no CQC registration and is <b>invisible to T3</b>. The Health and Care Act 2022 s.180 licensing scheme has <b>not commenced</b> — there is no register to read. Companies House is therefore the only national, dated record of an aesthetics business coming into existence. This tab mines 96 curated keywords (profhilo, polynucleotide, microneedling, HIFU, medispa…) across 8 SIC codes, whole-word matched. <b>Captures an estimated 20–35% of new aesthetics formation</b> (vs ~0% before); sole traders and mobile injectors — over half the entrants — remain unobservable. Read <i>latest</i> as a formation index, <b>not</b> a clinic count.</div>';

document.getElementById('cqbody').innerHTML=(RADAR.cqc&&RADAR.cqc.length?tableRows(RADAR.cqc,'New (12m)',{firstCol:'Clinic niche'}):'<div class="msg">No CQC data this run.</div>')+
  '<div class="note"><b>T3 · 6–18 months.</b> Locations newly registered with CQC, clustered by the words in their names. Scope: <b>Independent Healthcare</b> only. A clinic must register before it can legally trade, so this is committed capital. Counts are small (5–20 per niche) — a lead, not a measurement. See the Aesthetics tab for what this tier structurally cannot see.</div>';

document.getElementById('jbbody').innerHTML=tableRows(RADAR.jobs,'Live ads',{firstCol:'Specialty'})+
  '<div class="note"><b>T3 &middot; supporting, and the weakest tier.</b> Live clinician job ads (Adzuna). Adzuna serves no history, so growth accrues from snapshots this dashboard takes itself and will be blank until it does. Confirmation, not discovery.</div>';

function ivTable(){
  var IV=RADAR.invest||{};var ks=Object.keys(IV);
  if(!ks.length)return '<div class="msg">Investability not computed this run.</div>';
  var rows=ks.map(function(k){var v=IV[k];v._n=k;return v;});
  rows.sort(function(a,b){return (b.providers||0)-(a.providers||0);});
  var h='<table><thead><tr><th class="l">#</th><th class="l">Niche</th><th data-k="providers">Providers</th>'+
    '<th data-k="locations">Locations</th><th data-k="lpp">Sites / provider</th>'+
    '<th data-k="single">% single-site</th><th data-k="top5">Top-5 share</th><th class="l">Verdict</th></tr></thead><tbody>';
  rows.forEach(function(v,i){
    h+='<tr data-providers="'+(v.providers||0)+'" data-locations="'+(v.locations||0)+'" data-lpp="'+(v.lpp||0)+
       '" data-single="'+(v.single_site_pct||0)+'" data-top5="'+(v.top5_share||0)+'">'+
       '<td class="rk">'+(i+1)+'</td><td class="nm">'+v._n+'</td>'+
       '<td class="num">'+num(v.providers)+'</td><td class="num">'+num(v.locations)+'</td>'+
       '<td class="num">'+(v.lpp!=null?v.lpp.toFixed(2):'&ndash;')+'</td>'+
       '<td class="num">'+(v.single_site_pct!=null?Math.round(v.single_site_pct)+'%':'&ndash;')+'</td>'+
       '<td class="num">'+(v.top5_share!=null?Math.round(v.top5_share)+'%':'&ndash;')+'</td>'+
       '<td class="l">'+ivBadge(v)+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>Is it actually a roll-up?</b> Rising &ne; acquirable. This is the <b>entire active CQC population</b> (a stock), not new registrations (a flow). Many small single-site providers = fragmented = runway. A high top-5 share = someone already consolidated it. Under ~30 independent providers = there is no acquirable population, and the niche is marked "too small to roll up" however fast it is growing. '+
   '<b>Two biases, both flattering:</b> (1) a Provider ID is a legal entity, not an economic owner &mdash; a PE-backed group holding twelve Ltds looks like twelve independents; (2) aesthetics is under-counted because non-surgical clinics are not CQC-registrable at all.</div>';
}
document.getElementById('ivbody').innerHTML=ivTable();

document.querySelectorAll('.panel').forEach(wireSort);

// ---- T4 prescribing: batched by niche (16 requests, not 76 - OpenPrescribing 429s at ~60) ----
function loadPresc(){
  var niches=Object.keys(DRUGQ);
  return Promise.all(niches.map(function(niche){
    var codes=DRUGQ[niche];
    return fetch('https://openprescribing.net/api/1.0/spending/?code='+encodeURIComponent(codes)+'&format=json')
      .then(function(r){return r.ok?r.json():null;}).then(function(d){
        if(!d||d.length<15)return null;
        var v=d.map(function(x){return x.items;});var n=v.length;
        function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
        var last3=mn(n-3,n),prev3=mn(n-6,n-3),year3=mn(n-15,n-12);
        if(v[n-1]<100)return null;
        var names=codes.split(',').map(function(c){return (DRUGS[c]||[c])[0];});
        var treats=codes.split(',').map(function(c){return (DRUGS[c]||['','',''])[2];})
                        .filter(Boolean).slice(0,3).join('; ');
        return {name:niche,niche:niche,treats:names.join(', ')+' — '+treats,
                latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:pct(last3,prev3),
                g12:pct(last3,year3),date:d[n-1].date};
      }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){
    return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}
function finish(p){
  document.getElementById('prbody').innerHTML=(p.length?
    tableRows(p,'Items / mo',{drug:true,firstCol:'Niche (batched drugs)'}):'<div class="msg">Could not load prescribing.</div>')+
    '<div class="note"><b>T4 &middot; latest, and the highest-confidence.</b> NHS items dispensed in England (OpenPrescribing), <b>76 verified BNF codes batched into '+Object.keys(DRUGQ).length+' requests</b> &mdash; the endpoint sums codes server-side, keeping us under its ~60-call rate limit (a 429 renders as a false dash). <b>Hover a row</b> for the drugs behind it. Fetched live in your browser because OpenPrescribing blocks datacentre IPs'+(p.length?'; latest month '+p[0].date:'')+'. NHS prescribing is <b>not</b> private demand &mdash; it can run inverse to it, when the NHS restricts access and patients go private instead. 9 niches have no valid drug proxy and are marked n/a rather than dashed.</div>';
  wireSort(document.getElementById('pr'));
  document.getElementById('stbody').innerHTML=buildStack(p);
  wireSort(document.getElementById('st'));
}
loadPresc().then(finish).catch(function(){finish([]);});
</script></body></html>"""
