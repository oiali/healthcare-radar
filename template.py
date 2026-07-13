"""HTML template for the radar dashboard. Kept separate so the build script stays readable."""

TEMPLATE = r"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:1040px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px;flex-wrap:wrap}
.tab{padding:7px 13px;font-size:13px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.tab .t{font-size:10px;color:#aab0b8;font-weight:700;margin-right:5px}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:14px}.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 9px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}
th.sorted{color:#1e2530}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.niche{display:inline-block;font-weight:400;font-size:11.5px;color:#5b6470;background:#eef1f4;border-radius:20px;padding:1px 8px;margin-left:8px}
.newtag{background:#e6f1ff;color:#1c5fbf;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.found{background:#eafaf1;color:#1e7d46;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.drug{border-bottom:1px dotted #9aa4b0;cursor:help}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.note{font-size:12px;color:#8b929c;margin-top:12px}.msg{color:#8b929c;font-size:13px;padding:14px 6px}
.up{color:#1e7d46;font-weight:700}.dn{color:#c23b3b}.na{color:#c9ced4}
.st{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;white-space:nowrap}
.s1{background:#eef1f4;color:#5b6470}
.s2{background:#e6f1ff;color:#1c5fbf}
.s3{background:#eafaf1;color:#1e7d46}
.s4{background:#fdf1e3;color:#a76a1e}
.s0{background:#fde7e7;color:#c23b3b}
.mv{background:#f7fbff;border:1px solid #dce9f7;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:13.5px}
.mv b{color:#1c5fbf}.mv ul{margin:6px 0 0;padding-left:20px}.mv li{margin:3px 0}
.chain{font-size:12.5px;color:#6b7280;background:#f7f8f9;border-left:3px solid #d8dce1;padding:9px 12px;margin-bottom:14px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Server data {{UPDATED}} &middot; prescribing live in your browser &middot; click any column to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="st">The Stack</div>
  <div class="tab" data-p="tr"><span class="t">T1</span>Search interest</div>
  <div class="tab" data-p="in"><span class="t">T2</span>New companies</div>
  <div class="tab" data-p="cq"><span class="t">T3</span>New clinics</div>
  <div class="tab" data-p="jb"><span class="t">T3</span>Job ads</div>
  <div class="tab" data-p="pr"><span class="t">T4</span>Prescribing</div>
</div>
<div class="panel on" id="st"><div id="stbody" class="msg">Building the stack&hellip;</div></div>
<div class="panel" id="tr"><div id="trbody"></div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="cq"><div id="cqbody"></div></div>
<div class="panel" id="jb"><div id="jbbody"></div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live prescribing&hellip;</div></div>
</div>
<script>
var RADAR = {{DATA}};
var DRUGS={
"0601023AW":["Semaglutide","Weight loss / GLP-1","type-2 diabetes & obesity (Ozempic/Wegovy)"],
"0601023AZ":["Tirzepatide","Weight loss / GLP-1","type-2 diabetes & obesity (Mounjaro)"],
"0601023AB":["Liraglutide","Weight loss / GLP-1","obesity & diabetes (Saxenda/Victoza)"],
"0405010P0":["Orlistat","Weight loss / GLP-1","obesity (lipase inhibitor)"],
"0405020U0":["Naltrexone-bupropion","Weight loss / GLP-1","obesity (Mysimba)"],
"0404000U0":["Lisdexamfetamine","ADHD","ADHD - the adult-ADHD driver (Elvanse)"],
"0404000M0":["Methylphenidate","ADHD","ADHD stimulant"],
"0404000S0":["Atomoxetine","ADHD","ADHD (non-stimulant)"],
"0404000V0":["Guanfacine","ADHD","ADHD (non-stimulant)"],
"0604020K0":["Testosterone","Men's health / TRT","testosterone deficiency"],
"0604011Y0":["Tibolone","Menopause / HRT","menopausal symptoms"],
"0702010G0":["Estradiol (vaginal)","Menopause / HRT","vaginal atrophy / genitourinary menopause"],
"0604020C0":["Finasteride","Hair restoration","male-pattern hair loss & enlarged prostate"],
"0704050Z0":["Sildenafil","Sexual health / ED","erectile dysfunction"],
"0407042T0":["Erenumab","Migraine","migraine prevention (CGRP)"],
"0407042R0":["Fremanezumab","Migraine","migraine prevention (CGRP)"],
"0407041AD":["Rimegepant","Migraine","migraine treatment & prevention"],
"0407042U0":["Atogepant","Migraine","migraine prevention"],
"0704020AE":["Mirabegron","Bladder / continence","overactive bladder"],
"0606020Z0":["Denosumab","Osteoporosis / bone","osteoporosis (Prolia)"],
"1306010M0":["Isotretinoin","Dermatology / acne","severe acne (Roaccutane)"],
"0601023AG":["Dapagliflozin","Diabetes","type-2 diabetes, heart & kidney"],
"0601023AN":["Empagliflozin","Diabetes","type-2 diabetes, heart & kidney"],
"0403030Q0":["Sertraline","Mental health / psychiatry","depression & anxiety"],
"0401010AD":["Melatonin","Sleep","insomnia / sleep disorders"],
"0105030C0":["Risankizumab","Dermatology / acne","Crohn's disease, psoriasis"]};
var RISING=10;

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'<span class="na">&ndash;</span>':(x>=0?'+':'')+Math.round(x)+'%';}
function cell(x){if(x==null)return '<span class="na">&ndash;</span>';
  return '<span class="'+(x>=RISING?'up':(x<=-RISING?'dn':''))+'">'+(x>=0?'+':'')+Math.round(x)+'%</span>';}
function num(x){return (x==null?0:x).toLocaleString('en-GB');}
function trend(r){if(r.g12==null)return'no year-ago base';
  var s=r.g12>=25?'rising fast':r.g12>=5?'rising':r.g12>=-5?'roughly flat':'declining';
  return s+' (12-mth '+Math.round(r.g12)+'%)';}

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
    var nameCell;
    if(opts.drug){var tip=r.name+' — treats '+r.treats+'. '+trend(r);
      nameCell='<span class="drug" title="'+tip.replace(/"/g,'&quot;')+'">'+r.name+'</span>';}
    else nameCell=r.name;
    if(r.niche)nameCell+='<span class="niche">'+r.niche+'</span>';
    h+='<tr data-latest="'+r.latest+'" data-g1="'+(r.g1==null?-9999:r.g1)+'" data-g3="'+(r.g3==null?-9999:r.g3)+
      '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+nameCell+
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
function stage(t1,t2,t3,t4){
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
function buildStack(presc){
  var T1=agg(RADAR.trends),T2=agg(RADAR.inc),T3=agg(RADAR.cqc),T4=agg(presc);
  var names={};[T1,T2,T3,T4].forEach(function(o){for(var k in o)names[k]=1;});
  var rows=Object.keys(names).map(function(n){
    var a=T1[n],b=T2[n],c=T3[n],d=T4[n];var s=stage(a,b,c,d);
    return {n:n,t1:a,t2:b,t3:c,t4:d,cls:s[0],label:s[1],conv:s[2]};});
  rows.sort(function(x,y){
    if(y.conv!==x.conv)return y.conv-x.conv;
    return (y.t1==null?-9e9:y.t1)-(x.t1==null?-9e9:x.t1);});

  var h='<div class="chain"><b>Read left to right.</b> A niche is worth acting on when the <b>early</b> tiers are lit and the <b>late</b> ones are not — that is the window. Once T4 is rising, the demand is already being served.<br>'+
    '<b>T1 Search</b> (weeks, no lag) → <b>T2 New companies</b> (months) → <b>T3 New clinics</b> (6–18 mth) → <b>T4 NHS prescribing</b> (12+ mth, plus a 2-month publication lag).</div>';

  if(RADAR.moved&&RADAR.moved.length){
    h+='<div class="mv"><b>What moved in the last 7 days</b><ul>';
    RADAR.moved.forEach(function(m){
      h+='<li>'+m.niche+' — now firing on <b>'+m.to+'</b> of the 3 early tiers (was '+m.from+' on '+m.since+')</li>';});
    h+='</ul></div>';
  }

  h+='<table><thead><tr><th class="l">#</th><th class="l">Niche</th>'+
     '<th data-k="t1">T1 Search</th><th data-k="t2">T2 Companies</th>'+
     '<th data-k="t3">T3 Clinics</th><th data-k="t4">T4 Prescribing</th>'+
     '<th data-k="conv">Tiers</th><th class="l">Stage</th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    h+='<tr data-t1="'+(r.t1==null?-9999:r.t1)+'" data-t2="'+(r.t2==null?-9999:r.t2)+
       '" data-t3="'+(r.t3==null?-9999:r.t3)+'" data-t4="'+(r.t4==null?-9999:r.t4)+
       '" data-conv="'+r.conv+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.n+'</td>'+
       '<td class="num">'+cell(r.t1)+'</td><td class="num">'+cell(r.t2)+'</td>'+
       '<td class="num">'+cell(r.t3)+'</td><td class="num">'+cell(r.t4)+'</td>'+
       '<td class="num">'+r.conv+'/4</td><td class="l"><span class="st '+r.cls+'">'+r.label+'</span></td></tr>';});
  h+='</tbody></table><div class="note">All figures are <b>12-month growth</b>, volume-weighted across every item mapped to that niche. A dash means the source has no reading for that niche (absent, not zero). A tier "fires" at &ge;+10%. '+
     '<b>Caveat on the ordering:</b> the chain above is the default for a <i>demand-led</i> niche. For a <i>drug-led</i> one (GLP-1) NHS prescribing moves early — a new molecule creates the demand rather than following it. And for purely private niches (aesthetics, hair, IV) T4 never moves at all: read a dash there as "not applicable", not "not yet".</div>';
  return h;
}

document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term'}):'<div class="msg">Search data appears after the next weekly run.</div>')+
  '<div class="note"><b>T1 · earliest signal.</b> UK Google search interest (via SerpApi), refreshed weekly. The core terms are fixed, but terms tagged <span class="found">auto-found</span> were <b>discovered</b> by the supply-side tiers (new company and clinic names) and fed back in automatically — so this tab can surface niches nobody pre-listed.</div>';

document.getElementById('inbody').innerHTML=tableRows(RADAR.inc,'New (3m)',{firstCol:'Niche term'})+
  '<div class="note"><b>T2 · months.</b> Words and phrases rising fastest in the <b>names</b> of newly-incorporated health companies (SIC 86900/86220/96020/96040), last 3 months vs the same 3 months a year ago. Incorporating is the cheapest possible bet on a niche, which is why it moves early. Growth is blank where the year-ago base was under 3.</div>';

document.getElementById('cqbody').innerHTML=(RADAR.cqc&&RADAR.cqc.length?tableRows(RADAR.cqc,'New (12m)',{firstCol:'Clinic niche'}):'<div class="msg">No CQC data this run.</div>')+
  '<div class="note"><b>T3 · 6–18 months.</b> Every location newly registered with CQC, from CQC\'s monthly registration file, clustered by the words in its name. Scope is <b>Independent Healthcare</b> only — the private-pay universe. Social care, NHS trusts, NHS GPs and dental are excluded (churn, or formulaic naming that swamps the signal). A clinic must register before it can legally trade, so this is capital already committed. <b>Blind spot:</b> botox/filler-only clinics are not CQC-registrable, so aesthetics is structurally under-counted here. Counts are small (5–20 per niche) — treat as a lead, not a measurement.</div>';

document.getElementById('jbbody').innerHTML=tableRows(RADAR.jobs,'Live ads',{firstCol:'Specialty'})+
  '<div class="note"><b>T3 · supporting.</b> Live clinician job ads (Adzuna). Adzuna serves no history, so growth is computed from snapshots this dashboard takes itself — the 1/3/12-month columns fill in as that history accrues and will be blank until then. Weakest tier: confirmation, not discovery.</div>';

document.querySelectorAll('.panel').forEach(wireSort);

function loadPresc(){
  return Promise.all(Object.keys(DRUGS).map(function(code){var m=DRUGS[code];
    return fetch('https://openprescribing.net/api/1.0/spending/?code='+code+'&format=json')
      .then(function(r){return r.ok?r.json():null;}).then(function(d){
        if(!d||d.length<15)return null;var v=d.map(function(x){return x.items;});var n=v.length;
        function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
        var last3=mn(n-3,n),prev3=mn(n-6,n-3),year3=mn(n-15,n-12);
        if(v[n-1]<300)return null;
        return {name:m[0],niche:m[1],treats:m[2],latest:Math.round(v[n-1]),
                g1:pct(v[n-1],v[n-2]),g3:pct(last3,prev3),g12:pct(last3,year3),date:d[n-1].date};
      }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}
function finish(p){
  document.getElementById('prbody').innerHTML=(p.length?
    tableRows(p,'Items / mo',{drug:true,firstCol:'Drug'}):'<div class="msg">Could not load prescribing.</div>')+
    '<div class="note"><b>T4 · latest, and the highest-confidence.</b> Individual drugs (NHS items dispensed, England), each mapped to its niche. <b>Hover a drug</b> for what it treats. Fetched live in your browser'+(p.length?', latest month '+p[0].date:'')+'. NHS prescribing is <b>not</b> private demand — it can run inverse to it, when the NHS restricts access and patients go private instead.</div>';
  wireSort(document.getElementById('pr'));
  document.getElementById('stbody').innerHTML=buildStack(p);
  wireSort(document.getElementById('st'));
}
loadPresc().then(finish).catch(function(){finish([]);});
</script></body></html>"""
