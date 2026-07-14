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
.dm{font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px;white-space:nowrap}
.dm-boom{background:#e6f1ff;color:#1c5fbf}.dm-grow{background:#eafaf1;color:#1e7d46}
.dm-flat{background:#eef1f4;color:#5b6470}.dm-fall{background:#fde7e7;color:#c23b3b}
.dm-unk{background:#f1f2f4;color:#9aa0a8}
.sp{font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px;white-space:nowrap}
.sp-frag{background:#eafaf1;color:#1e7d46}.sp-fill{background:#fdf1e3;color:#a76a1e}
.sp-cons{background:#fde7e7;color:#c23b3b}.sp-none{background:#eef1f4;color:#5b6470}
.sp-unk{background:#f1f2f4;color:#9aa0a8}
.el{font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;white-space:nowrap}
.el-buy{background:#1e7d46;color:#fff}.el-build{background:#1c5fbf;color:#fff}
.el-neither{background:#eef1f4;color:#8b929c}
.den{font-size:10.5px;color:#9aa0a8;font-variant-numeric:tabular-nums;white-space:nowrap}
.thin{color:#a76a1e;font-size:10.5px;font-style:italic;white-space:nowrap}
.auto{background:#f4eefb;color:#6b4a9e;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.cav{font-size:12px;color:#8a6d3b;background:#fff8ec;border-left:3px solid #e8c886;
     padding:7px 11px;margin:4px 0 0}
.cav b{color:#7a5d2b}
td.q{max-width:300px}
.mv{background:#f7fbff;border:1px solid #dce9f7;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:13.5px}
.mv b{color:#1c5fbf}.mv ul{margin:6px 0 0;padding-left:20px}.mv li{margin:3px 0}
.chain{font-size:12.5px;color:#6b7280;background:#f7f8f9;border-left:3px solid #d8dce1;padding:9px 12px;margin-bottom:14px}
.warn{font-size:12.5px;color:#8a6d3b;background:#fff8ec;border-left:3px solid #e8c886;padding:9px 12px;margin-bottom:14px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Server data {{UPDATED}}
&middot; what is rising, and how early &middot; click any column to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="st">The Stack</div>
  <div class="tab" data-p="ad">Adoption</div>
  <div class="tab" data-p="dc">Discovery</div>
  <div class="tab" data-p="ct">Catalysts</div>
  <div class="tab" data-p="wt"><span class="t">T0</span>NHS waits</div>
  <div class="tab" data-p="tr"><span class="t">T1</span>Search</div>
  <div class="tab" data-p="in"><span class="t">T2</span>New companies</div>
  <div class="tab" data-p="cq"><span class="t">T3</span>New clinics</div>
  <div class="tab" data-p="pr"><span class="t">T4</span>Prescribing</div>
  <div class="tab" data-p="iv">Market structure</div>
</div>
<div class="panel on" id="st"><div id="stbody" class="msg">Building the stack&hellip;</div></div>
<div class="panel" id="ad"><div id="adbody"></div></div>
<div class="panel" id="dc"><div id="dcbody"></div></div>
<div class="panel" id="ct"><div id="ctbody"></div></div>
<div class="panel" id="wt"><div id="wtbody"></div></div>
<div class="panel" id="tr"><div id="trbody"></div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="cq"><div id="cqbody"></div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live prescribing&hellip;</div></div>
<div class="panel" id="iv"><div id="ivbody"></div></div>
</div>
<script>
var RADAR = {{DATA}};
var DRUGQ = RADAR.drugq||{};          // niche -> comma-separated BNF codes (batched: 16 calls, not 76)
var DRUGS = RADAR.drugs||{};          // code -> [name, niche, treats]
var NOPRESC = RADAR.nopresc||[];      // niches with NO valid NHS prescribing proxy -> show n/a, not a dash
var RISING = 10;
var STATUS = RADAR.status||{};
var SRCNAME = {waits:'NHS waiting times', trends:'Google search', inc:'New companies',
  aes:'Aesthetics miner', cqc:'New CQC clinics', invest:'Market structure',
  disc:'Discovery (open layer)', presc:'NHS prescribing', drugdisc:'Rising drugs',
  topen:'Rising Google queries', cats:'Medicine licences'};
function failedBanner(){
  var bad=[];for(var k in STATUS){if(STATUS[k]==='failed')bad.push(SRCNAME[k]||k);}
  if(!bad.length)return '';
  return '<div class="warn"><b>'+bad.length+' source'+(bad.length>1?'s':'')+' failed today: '+
    bad.join(', ')+'.</b> Where you see an empty tab or a dash for these, it means <b>we could '+
    'not fetch the data</b> &mdash; not that there is nothing there. Do not read a failure as a zero.</div>';
}
// A source that FAILED must say so, not print a cheerful "nothing found".
function srcMsg(key, emptyMsg){
  if(STATUS[key]==='failed')
    return '<div class="warn"><b>'+(SRCNAME[key]||key)+' failed to load today.</b> This is not '+
           'an empty result &mdash; the source could not be reached. Check the run log.</div>';
  return '<div class="msg">'+emptyMsg+'</div>';
}

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'<span class="na">&ndash;</span>':(x>=0?'+':'')+Math.round(x)+'%';}
function cell(x,na){if(x==null)return na?'<span class="nap">n/a</span>':'<span class="na">&ndash;</span>';
  return '<span class="'+(x>=RISING?'up':(x<=-RISING?'dn':''))+'">'+(x>=0?'+':'')+Math.round(x)+'%</span>';}
function num(x){return (x==null?0:x).toLocaleString('en-GB');}
// ------------------------------------------------- a % is a lie without its base
// "+200%" is two extra clinics. "+159%" is a name typed into a form fifty times.
// So: no percentage is printed unless its base clears MIN_BASE, and no percentage is
// believed unless it also clears one standard deviation of Poisson counting noise on
// that base (100/sqrt(base) percent).
//
//   base 2   -> +/-71%   nothing on a base of 2 can ever be believed
//   base 10  -> +/-32%
//   base 40  -> +/-16%
//   base 400 -> +/-5%
//
// One sigma is a WEAK bar (~84% one-sided). Two sigma is the scientific bar and would
// silence almost every tier on this dashboard, because the counts really are that
// small. One sigma is the honest compromise, and it is stated rather than hidden.
var MIN_BASE=10;
function noisePct(b){return (!b||b<=0)?null:100*Math.sqrt(b)/b;}
function showPct(b){
  if(!b)return true;
  if(b.index)return true;
  return (b.base==null)?true:(b.base>=MIN_BASE);
}
function fires(g,b){
  if(g==null)return false;
  b=b||{};
  var n=b.base,ix=!!b.index;
  if(!ix&&n!=null&&n<MIN_BASE)return false;
  var th=RISING;
  if(!ix&&n){var nf=noisePct(n);if(nf!=null&&nf>th)th=nf;}
  return g>=th;
}
// The renderer. Always prints the two counts. Prints the % only if it means something.
function cellD(g,b,na){
  b=b||{};
  var den='';
  if(b.base!=null&&b.latest!=null){
    den='<div class="den">'+(b.index?'index ':'')+num(b.base)+' &rarr; '+num(b.latest)+'</div>';
  }
  if(g==null){
    return (na?'<span class="nap">n/a</span>':'<span class="na">&ndash;</span>')+den;
  }
  if(!showPct(b)){
    // Base under the floor: show the raw counts and REFUSE to show a percentage.
    return '<span class="thin">too thin for a %</span>'+den;
  }
  var lit=fires(g,b);
  var cls=lit?'up':(g<=-RISING?'dn':'');
  var pc='<span class="'+cls+'">'+(g>=0?'+':'')+Math.round(g)+'%</span>';
  // Clears +10% but is inside its own noise band -> shown, greyed, not "firing".
  if(!lit&&g>=RISING)pc='<span class="na" title="inside the noise band for a base of '
    +b.base+'">'+(g>=0?'+':'')+Math.round(g)+'%</span>';
  return pc+den;
}

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
    var tag=r.isnew?'<span class="newtag">new</span>':
      (r.found?'<span class="auto" title="Auto-discovered from the supply tiers (T2/T3). '+
        'Does NOT count toward conviction — it would be confirming itself.">auto-found '+
        '· no vote</span>':'');
    var nm=r.name;
    if(opts.drug&&r.treats)nm='<span class="drug" title="'+
      String(r.treats).replace(/"/g,'&quot;')+'">'+r.name+'</span>';
    if(r.niche)nm+='<span class="niche">'+r.niche+'</span>';
    // Recover the year-ago base: base = latest / (1 + g12/100).
    var B=null;
    if(r.g12!=null&&r.latest!=null){
      var bs=r.latest/(1+r.g12/100);
      if(isFinite(bs)&&bs>=0)B={base:Math.round(bs),latest:r.latest,index:!!opts.index};
    }
    h+='<tr data-latest="'+(r.latest||0)+'" data-g1="'+(r.g1==null?-9999:r.g1)+
      '" data-g3="'+(r.g3==null?-9999:r.g3)+'" data-g12="'+(r.g12==null?-9999:r.g12)+
      '"><td class="rk">'+(i+1)+'</td><td class="nm">'+nm+
      '</td><td class="num">'+num(r.latest)+'</td><td class="num">'+fmt(r.g1)+
      '</td><td class="num">'+fmt(r.g3)+'</td><td class="num g12">'+
      cellD(r.g12,B)+'</td><td class="l">'+tag+'</td></tr>';});
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
// ---------------------------------------------------------------- DENOMINATORS
// Every source row carries `latest` and `g12` but NOT the year-ago count it was
// divided by. That count is recoverable exactly, because g12 = (latest/base - 1)*100:
//
//        base = latest / (1 + g12/100)
//
// So we can print a real denominator next to every percentage WITHOUT touching
// pull_and_build.py. Rows with a null g12 have no recoverable base and are excluded
// from both the numerator and the denominator - never counted on one side only.
//
// opts.index          -> this tier is a 0-100 relative index (T1 search), not a count.
//                        Counting noise does not apply and the base is not a "number
//                        of things", so it is labelled differently.
// opts.independentOnly -> drop rows tagged found=true. Those search terms were
//                        AUTO-DISCOVERED from T2/T3 by discovered_terms(). Letting
//                        them vote would mean T1 confirming what T2 told it to look
//                        for. They are still counted in `items` and still displayed.
function aggB(rows,opts){
  opts=opts||{};
  var m={};
  (rows||[]).forEach(function(r){
    var n=r.niche;if(!n)return;
    if(!m[n])m[n]={latest:0,base:0,items:0,indep:0};
    var a=m[n];a.items++;
    if(opts.independentOnly&&r.found)return;      // counted, but gets no vote
    a.indep++;
    if(r.g12==null)return;                        // no growth => no recoverable base
    var L=(r.latest==null?0:r.latest);
    var B=L/(1+r.g12/100);
    if(!isFinite(B)||B<0)return;
    a.latest+=L;a.base+=B;
  });
  var g={},b={};
  for(var k in m){
    var a=m[k];
    b[k]={latest:Math.round(a.latest),base:Math.round(a.base),
          items:a.items,independent_items:a.indep,index:!!opts.index};
    g[k]=(a.base>0)?((a.latest/a.base-1)*100):null;
  }
  return {g:g,b:b};
}
// ============================================================ THE TRACKER READ
// This is a TREND TRACKER. The question it answers is:
//     what is rising, and HOW EARLY am I seeing it?
// Not "should I buy it". Market structure is shown as CONTEXT, in its own column,
// and it never decides the verdict.
//
// The demand chain, earliest -> latest:
//   T1 search        people start looking            weeks, no lag
//   T2 new companies founders bet on it              months
//   T3 new clinics   capacity gets built             6-18 months
//   T4 prescribing   the NHS is dispensing it        12+ months
//   (T0 NHS waits is the upstream PRESSURE that drives people private at all.)
//
// The earliest tier that is firing tells you where you are in that chain. If only
// T1 is lit you are very early and it might be nothing. If T4 is lit it already
// happened. That is the whole read.
var BOOM=40.0, FALLING=-10.0;

function entryRate(iv){
  if(!iv)return null;
  var stock=iv.locations, nu=iv.new_12m;
  if(stock==null||nu==null||stock<=0)return null;
  return 100*nu/stock;
}
// demand trajectory from the two demand tiers only (T0 pressure + T1 intent)
function readDemand(t0,t1,B){
  var lit=[];
  if(fires(t1,B.t1))lit.push(t1);
  if(fires(t0,B.t0))lit.push(t0);
  if(!lit.length){
    if(t1==null&&t0==null)return 'unknown';
    var v=(t1!=null)?t1:t0;
    return (v<=FALLING)?'falling':'flat';
  }
  return (Math.max.apply(null,lit)>=BOOM)?'booming':'growing';
}
// market STRUCTURE - context only. Never gates the verdict.
function readStructure(iv){
  if(!iv)return ['unknown',null];
  var er=entryRate(iv);
  var v=(iv.verdict||'').toLowerCase();
  if(/too small/.test(v))return ['tiny',er];
  if(/consolidat/.test(v))return ['consolidated',er];
  if(/infant|gold rush/.test(v))return ['rushing',er];
  if(/fragmented/.test(v))return ['fragmented',er];
  return ['unknown',er];
}
var STLABEL={
  early:      '1 · Search only — very early, may be nothing',
  emerging:   '2 · Emerging — founders are moving in',
  building:   '3 · Building out — capacity arriving',
  mainstream: '4 · Mainstream — it has already happened',
  cooling:    'Cooling — past peak',
  quiet:      '— nothing firing',
  nodata:     'Not enough data'
};
var STCLS={early:'s1',emerging:'s2',building:'s3',mainstream:'s4',
           cooling:'s0',quiet:'s1',nodata:'s1'};
// rank: how EARLY, i.e. how much of the chain is still ahead of you. Highest = earliest.
var STRANK={emerging:5,early:4,building:3,mainstream:2,cooling:1,quiet:0,nodata:0};

function readStage(n,t0,t1,t2,t3,t4,B){
  var f1=fires(t1,B.t1), f2=fires(t2,B.t2), f3=fires(t3,B.t3), f4=fires(t4,B.t4);
  var na4=NOPRESC.indexOf(n)>=0;
  var lit=[f1,f2,f3,f4].filter(Boolean).length;
  var d=readDemand(t0,t1,B);
  var q;
  // The LATEST tier that is firing tells you how far this has already travelled.
  // (The earliest one tells you nothing about lateness - that was the bug.)
  if(lit===0)                       q = (t1!=null||t2!=null||t3!=null)?'quiet':'nodata';
  else if(f4)                       q = (f1||f2) ? 'mainstream' : 'cooling';
  else if(f3)                       q = (f1||f2) ? 'building'   : 'cooling';
  else if(f2)                       q = 'emerging';
  else                              q = 'early';
  if(d==='falling'&&!f1&&!f2)       q = 'cooling';
  var cav=[];
  if(f4&&!na4)cav.push('T4 is ambiguous: NHS prescribing can rise because the condition is growing, OR because the NHS started funding it — which shrinks the private market. It votes, but read it twice.');
  if(B.t1&&B.t1.independent_items===0&&B.t1.items>0)cav.push('Every T1 term here was auto-discovered from T2/T3, so T1 is confirming what the supply tiers told it to search for. Treated as no vote.');
  if(q==='early')cav.push('Search interest with nothing behind it is the cheapest possible signal. Most of these go nowhere.');
  return {q:q,demand:d,lit:lit,label:STLABEL[q],cls:STCLS[q],rank:STRANK[q],caveats:cav,na4:na4};
}
var DMCLS={booming:'dm-boom',growing:'dm-grow',flat:'dm-flat',falling:'dm-fall',
           unknown:'dm-unk'};
var STRUCTTXT={fragmented:'many small operators',rushing:'gold rush — lots of new entrants',
               consolidated:'already consolidated',tiny:'very few operators',
               unknown:'unknown'};
var STRUCTCLS={fragmented:'sp-frag',rushing:'sp-fill',consolidated:'sp-cons',
               tiny:'sp-none',unknown:'sp-unk'};
function ivBadge(v){
  if(!v)return '<span class="iv iv-na">no data</span>';
  // Deliberately NOT rendering investability2's own verdict string - it is written in
  // roll-up language ("real roll-up runway"). This is a trend tracker; market structure
  // is context. So we describe the structure and let the reader draw the conclusion.
  var st=readStructure(v), k=st[0], er=st[1];
  var txt=STRUCTTXT[k]||'unknown';
  if(er!=null)txt+=' &middot; '+Math.round(er)+'% opened in the last year';
  var tip=((v.owners_economic||v.providers||'?')+' operators, '+(v.locations||'?')+' sites'+
    (v.single_site_pct!=null?', '+Math.round(v.single_site_pct)+'% single-site':''));
  return '<span class="sp '+(STRUCTCLS[k]||'sp-unk')+'" title="'+tip.replace(/"/g,'&quot;')+'">'+txt+'</span>';
}

function buildStack(presc){
  var A0=aggB(RADAR.waits), A1=aggB(RADAR.trends,{index:true,independentOnly:true}),
      A2=aggB((RADAR.inc||[]).concat(RADAR.aes||[])), A3=aggB(RADAR.cqc), A4=aggB(presc);
  var IV=RADAR.invest||{};
  var names={};[A0.g,A1.g,A2.g,A3.g,A4.g].forEach(function(o){for(var k in o)names[k]=1;});
  for(var k in IV)names[k]=1;

  var rows=Object.keys(names).map(function(n){
    var B={t0:A0.b[n],t1:A1.b[n],t2:A2.b[n],t3:A3.b[n],t4:A4.b[n]};
    var s=readStage(n,A0.g[n],A1.g[n],A2.g[n],A3.g[n],A4.g[n],B);
    var st=readStructure(IV[n]);
    return {n:n,t0:A0.g[n],t1:A1.g[n],t2:A2.g[n],t3:A3.g[n],t4:A4.g[n],B:B,
            s:s,struct:st[0],er:st[1],iv:IV[n]};});

  // sort by HOW EARLY you are seeing it, then by how hard the earliest tier is moving
  rows.sort(function(x,y){
    if(y.s.rank!==x.s.rank)return y.s.rank-x.s.rank;
    var xa=(x.t1==null?-9e9:x.t1), ya=(y.t1==null?-9e9:y.t1);
    if(ya!==xa)return ya-xa;
    return (y.t2==null?-9e9:y.t2)-(x.t2==null?-9e9:x.t2);});

  var h=failedBanner();
  h+='<div class="chain"><b>What is rising, and how early are you seeing it?</b> '+
    'Read left to right: <b>T1 search</b> (weeks) &rarr; <b>T2 new companies</b> (months) &rarr; '+
    '<b>T3 new clinics</b> (6&ndash;18 mth) &rarr; <b>T4 NHS prescribing</b> (12+ mth). '+
    '<b>T0 NHS waits</b> sits upstream of all of it &mdash; it is the pressure that pushes people private in the first place.<br>'+
    'The <b>earliest tier that is firing</b> tells you where in that chain you are. Only T1 lit = very early, and probably nothing. '+
    'T4 lit = it already happened. Sorted so the <b>earliest</b> things are at the top. '+
    '<b>Market structure</b> is context, not a verdict.</div>';

  h+='<div class="warn"><b>Before you trust a cell.</b> The tier ordering is <b>not proven</b> &mdash; and worse, it is partly an artefact of the measurement: on synthetic data where the true lead is <b>zero</b>, the estimator still &ldquo;finds&rdquo; T1 leading T2 by ~2 months, simply because thin, noisy series take longer to cross a threshold. '+
    'Every % is printed with its base (<span class="den">was &rarr; now</span>); anything under a base of 10 shows <span class="thin">too thin for a %</span> instead of a number, and a % inside its own counting-noise band is greyed out rather than treated as real. '+
    'A dash = no reading. <i>n/a</i> = that source structurally cannot see this niche (e.g. aesthetics has no NHS drug).</div>';

  if(RADAR.moved&&RADAR.moved.length){
    h+='<div class="mv"><b>What moved in the last 7 days</b><ul>';
    RADAR.moved.forEach(function(m){
      h+='<li>'+m.niche+' — now firing on <b>'+m.to+'</b> of the 4 tiers (was '+m.from+' on '+m.since+')</li>';});
    h+='</ul></div>';
  }

  h+='<table><thead><tr><th class="l">#</th><th class="l">Niche</th>'+
     '<th data-k="t0">T0 NHS wait</th><th data-k="t1">T1 Search</th><th data-k="t2">T2 Companies</th>'+
     '<th data-k="t3">T3 Clinics</th><th data-k="t4">T4 Prescribing</th>'+
     '<th data-k="lit">Tiers</th><th class="l">Demand</th><th class="l q">How early</th>'+
     '<th class="l">Market structure</th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    var cav=r.s.caveats.length?'<div class="cav">'+r.s.caveats.join(' ')+'</div>':'';
    var stx=STRUCTTXT[r.struct]||'unknown';
    if(r.er!=null)stx+=' · '+Math.round(r.er)+'% opened in the last yr';
    h+='<tr data-t0="'+(r.t0==null?-9999:r.t0)+'" data-t1="'+(r.t1==null?-9999:r.t1)+
       '" data-t2="'+(r.t2==null?-9999:r.t2)+'" data-t3="'+(r.t3==null?-9999:r.t3)+
       '" data-t4="'+(r.t4==null?-9999:r.t4)+'" data-lit="'+r.s.lit+
       '"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.n+'</td>'+
       '<td class="num">'+cellD(r.t0,r.B.t0)+'</td><td class="num">'+cellD(r.t1,r.B.t1)+'</td>'+
       '<td class="num">'+cellD(r.t2,r.B.t2)+'</td><td class="num">'+cellD(r.t3,r.B.t3)+'</td>'+
       '<td class="num">'+cellD(r.t4,r.B.t4,r.s.na4)+'</td>'+
       '<td class="num">'+r.s.lit+'/4</td>'+
       '<td class="l"><span class="dm '+(DMCLS[r.s.demand]||'dm-unk')+'">'+r.s.demand+'</span></td>'+
       '<td class="l q"><span class="st '+r.s.cls+'">'+r.s.label+'</span>'+cav+'</td>'+
       '<td class="l"><span class="sp '+(STRUCTCLS[r.struct]||'sp-unk')+'" title="'+
         (r.iv?((r.iv.owners_economic||r.iv.providers||'?')+' operators, '+(r.iv.locations||'?')+' sites'):'')+
         '">'+stx+'</span></td></tr>';});
  h+='</tbody></table><div class="note">All figures are <b>12-month growth</b>, pooled across every item mapped to that niche (counts summed, then divided &mdash; not an average of percentages). '+
     '<b>T1 terms that were auto-discovered from T2/T3 are shown but get no vote</b>, otherwise T1 would be confirming what the supply tiers told it to look for. '+
     '<b>T0 covers consultant-led elective NHS care only</b>, so it is structurally blind to weight-loss and ADHD &mdash; two of the biggest private-pay niches. '+
     '<b>Market structure</b> comes from the entire active CQC population (a stock, not a flow) and is grouped by <i>economic owner</i>, not legal entity. It tells you whether a niche is crowded, not whether it is good.</div>';
  return h;
}

document.getElementById('wtbody').innerHTML=(RADAR.waits&&RADAR.waits.length?
  tableRows(RADAR.waits,'Waiting',{firstCol:'NHS specialty'}):srcMsg('waits','No NHS RTT rows.'))+
  '<div class="note"><b>T0 · the causal driver.</b> NHS England Referral-to-Treatment waits. Growth is measured on the <b>count waiting over 18 weeks</b> — deterioration in NHS access — not on total volume. When the NHS stops coping, patients go private; everything else on this dashboard is downstream of this. <b>Limits:</b> England only, ~6 weeks in arrears, consultant-led elective care only — so it is <b>blind to weight-loss and ADHD</b>, the two biggest private-pay niches. g1 is noisy (non-submitting trusts create fake swings); trust g3/g12.</div>';

document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term',index:true}):
  srcMsg('trends','Search data appears after the next weekly run.'))+
  '<div class="note"><b>T1 &middot; the only early DEMAND signal on this dashboard.</b> '+
  'UK Google search interest (SerpApi), weekly.<br>'+
  '<b>Terms tagged <span class="auto">auto-found &middot; no vote</span> are '+
  'contaminated on purpose.</b> They were discovered by the SUPPLY tiers (T2 new company '+
  'names, T3 new clinic names) and fed back into the search list by '+
  '<code>discovered_terms()</code>. That is a good way to SURFACE a niche nobody '+
  'pre-listed. It is a worthless way to CONFIRM one: if T1 only lights up because T2 told '+
  'it what to search for, then "T1 and T2 agree" is <b>plumbing, not evidence</b>. '+
  'So they are shown, and they are given <b>zero weight</b> in the Stack’s demand '+
  'read and in any tier count.<br>'+
  '<b>Limit:</b> this is a 0–100 <i>relative</i> index over a rolling 12-month '+
  'window. It cannot see a multi-year build-up, and a term that has been flat-but-huge '+
  'for three years reads the same as a term nobody searches for.</div>';

function t2Table(){
  var R=(RADAR.inc||[]).concat(RADAR.aes||[]);
  if(!R.length)return srcMsg('inc','No new-company terms cleared the floor.');
  var b=(RADAR.diag||{}).t2_base||{};
  var h='';
  if(b.growth!=null){
    h+='<div class="warn"><b>Base rate: ALL new health companies grew '+
      (b.growth>=0?'+':'')+Math.round(b.growth)+'% over the same window</b> ('+
      num(b.prior)+' &rarr; '+num(b.now)+'). Every figure below is <b>net of that</b> &mdash; '+
      'it is how much faster than health incorporations as a whole. '+
      'Without this control T2 is not a demand signal: the UK register swings &plusmn;10&ndash;12% a year on '+
      'Companies House fee changes alone (&pound;12&rarr;&pound;50 in May 2024, &rarr;&pound;100 in Feb 2026) and on compulsory ID verification (Nov 2025).</div>';
  }
  h+='<table><thead><tr><th class="l">#</th><th class="l">Niche term</th>'+
    '<th data-k="latest">New (3m)</th><th data-k="raw">Raw growth</th>'+
    '<th data-k="g12">vs base rate</th><th class="l">95% interval</th></tr></thead><tbody>';
  R.forEach(function(r,i){
    var nm=r.name+(r.niche?'<span class="niche">'+r.niche+'</span>':'')+
      (r.isnew?'<span class="newtag">new</span>':'');
    var ci=(r.ci_lo!=null&&r.ci_hi!=null)?
      ('<span class="den">'+(r.ci_lo>=0?'+':'')+Math.round(r.ci_lo)+'% to '+
       (r.ci_hi>=0?'+':'')+Math.round(r.ci_hi)+'%</span>'+
       (r.ci_lo<=0?' <span class="thin">includes zero</span>':'')):
      '<span class="na">&ndash;</span>';
    h+='<tr data-latest="'+(r.latest||0)+'" data-raw="'+(r.raw_g12==null?-9999:r.raw_g12)+
       '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td>'+
       '<td class="nm">'+nm+'</td><td class="num">'+num(r.latest)+'</td>'+
       '<td class="num">'+fmt(r.raw_g12)+'</td><td class="num g12">'+fmt(r.g12)+'</td>'+
       '<td class="l">'+ci+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>T2 &middot; months. The weakest tier on the dashboard, and here is why.</b> '+
    'An incorporation costs &pound;100 and proves only that somebody typed a name into a form. It measures the <b>cost of entry</b> at least as much as demand &mdash; so it will reliably point you at the <i>cheapest</i> niche to enter, which is not the same as the best one.<br>'+
    '<b>The counts are tiny, so the intervals are enormous.</b> A move from 13 to 29 companies reads as "+123%", but its 95% interval is <b>+16% to +329%</b>. Any interval that includes zero means the term has not been shown to be rising at all.<br>'+
    '<b>Known artefacts we cannot fully strip:</b> a franchise filing 16 regional companies at once; clinicians incorporating personal service companies for tax reasons; a rebranding fashion. All three produce exactly this signal.<br>'+
    '<b>Aesthetics terms are folded in here</b> &mdash; not because aesthetics is special, but because purely cosmetic clinics are <b>not CQC-registrable</b> (DHSC: <i>"TDDI does not include interventions carried out purely for cosmetic purposes"</i>), so without this miner that niche would read as zero supply.</div>';
}
document.getElementById('inbody').innerHTML=t2Table();

document.getElementById('cqbody').innerHTML=(RADAR.cqc&&RADAR.cqc.length?tableRows(RADAR.cqc,'New (12m)',{firstCol:'Clinic niche'}):srcMsg('cqc','No CQC registrations in the window.'))+
  '<div class="note"><b>T3 · 6–18 months.</b> Locations newly registered with CQC, clustered by the words in their names. Scope: <b>Independent Healthcare</b> only. A clinic must register before it can legally trade, so this is committed capital. Counts are small (5–20 per niche) — a lead, not a measurement. See the Aesthetics tab for what this tier structurally cannot see.</div>'+
  ' <b>Read a clinic registration as capital committed.</b> Somebody has spent real money '+
  'and waited months for CQC. That is a much harder signal than a company registration &mdash; '+
  'and a much later one.';

function ivTable(){
  var IV=RADAR.invest||{};var ks=Object.keys(IV);
  if(!ks.length)return srcMsg('invest','Market structure not computed this run.');
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
  return h+'</tbody></table><div class="note"><b>Who is actually in this niche?</b> Context for the Stack, not a verdict. This is the <b>entire active CQC population</b> (a stock, not a flow), grouped by <b>economic owner</b> &mdash; providers sharing a director or registered address are merged, so a group holding twelve Ltds counts once. Many small operators = a fragmented, competitive niche. A high top-5 share = someone big already owns it. The <b>entry rate</b> (share of the standing stock that registered in the last year) separates a genuine gold rush from a settled market: ~22% of weight-loss clinics opened last year; ~5% of dental practices did. <b>Two blind spots:</b> non-surgical aesthetics clinics are not CQC-registrable at all, so aesthetics is under-counted here; and owner-merging can only merge, never split, so the operator count is an upper bound.</div>'+
  ' <b>What this tab does NOT tell you:</b> whether a niche is any good. It only tells you '+
  'who is in it. A fragmented niche can be fragmented because it is new and nobody has '+
  'scaled yet, or because it is old and nobody ever will. The <b>entry rate</b> column '+
  'separates those two: it is the share of the standing stock that registered in the '+
  'last year.';
}
document.getElementById('ivbody').innerHTML=ivTable();

function discTable(){
  var D=RADAR.disc||[];
  if(!D.length)return srcMsg('disc','Nothing unclassified cleared the bar this run. That is a real result: no phrase had enough unrelated operators, across enough regions, rising by more than arrival noise can explain.');
  var h='<table><thead><tr><th class="l">#</th><th class="l">Phrase</th>'+
    '<th data-k="ops">Operators</th><th data-k="prior">A year ago</th>'+
    '<th data-k="regions">Regions</th><th data-k="growth">Growth</th>'+
    '<th class="l">Age</th><th class="l q">Why it is here</th></tr></thead><tbody>';
  D.forEach(function(r,i){
    var g=(r.growth_yoy==null)?'<span class="na">&ndash;</span>':
      '<span class="'+(r.growth_yoy>=25?'up':'')+'">'+(r.growth_yoy>=0?'+':'')+Math.round(r.growth_yoy)+'%</span>';
    var tag=r.emerging?'<span class="newtag">new</span>':(r.established?'':'');
    h+='<tr data-ops="'+(r.distinct_operators||0)+'" data-prior="'+(r.operators_prior_12m||0)+
       '" data-regions="'+(r.regions||0)+'" data-growth="'+(r.growth_yoy==null?-9999:r.growth_yoy)+
       '"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.phrase+' '+tag+'</td>'+
       '<td class="num">'+num(r.distinct_operators)+'</td>'+
       '<td class="num">'+num(r.operators_prior_12m)+'</td>'+
       '<td class="num">'+num(r.regions)+'</td>'+
       '<td class="num g12">'+g+'</td><td class="l">'+(r.age||'')+'</td>'+
       '<td class="l q">'+(r.why||'')+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>The open layer &mdash; the only place a niche you have never heard of can appear.</b> Every other tab re-ranks 25 <i>pre-defined</i> niches and by construction can never surface a new one. This is the <b>residue</b>: phrases mined from new company and clinic names that match <b>no</b> known niche.<br>'+
    '<b>How a real service is told apart from a brand:</b> a service is used by many unrelated operators; a brand is used many times by one. So a phrase must appear across <b>&ge;6 distinct operators</b>, in <b>&ge;3 regions</b>, at a low mentions-per-operator ratio, and have risen by more than arrival noise can explain (z &ge; 2.4 &mdash; a plain "+25% growth" rule surfaced 22 junk rows per run: surnames, towns, brand words). That kills brands, franchises, surnames and place names <b>structurally</b>, not with a blocklist.<br>'+
    '<b>What it can never see:</b> an existing clinic quietly adding a service line. That files no company and registers no location &mdash; it just changes a page on its website. Plausibly how ADHD actually spread. So this catches the second wave, not the first.</div>';
}
document.getElementById('dcbody').innerHTML=discTable()+risingQ()+drugDisc();
document.getElementById('ctbody').innerHTML=catTable();
document.getElementById('adbody').innerHTML=panelTable();

// ADOPTION, not entry. The one sensor here that can see an EXISTING clinic quietly
// adding a service - which files no company, registers no location, and is invisible
// to every other tab. Plausibly how ADHD actually spread.
function panelTable(){
  var P=RADAR.panel||[];
  if(!P.length)return srcMsg('panel','The panel is still backfilling. It walks a fixed cohort of real UK clinic websites through the Internet Archive on a budget, so it fills in over several runs before it can report a trend.');
  var h='<table><thead><tr><th class="l">#</th><th class="l">Service</th>'+
    '<th data-k="now">Clinics offering it</th><th data-k="prior">A year ago</th>'+
    '<th data-k="growth">Growth</th><th class="l">First seen</th>'+
    '<th class="l q">Who just added it</th></tr></thead><tbody>';
  P.forEach(function(r,i){
    // panel.py returns growth as a RATIO (1.0 = doubled), not a percentage.
    var gp=(r.growth==null)?null:r.growth*100;
    var g=(gp==null)?'<span class="na">&ndash;</span>':
      '<span class="'+(gp>=25?'up':'')+'">'+(gp>=0?'+':'')+Math.round(gp)+'%</span>';
    var who=(r.new_adopters||[]).slice(0,3).join(', ');
    h+='<tr data-now="'+(r.clinics_now||0)+'" data-prior="'+(r.clinics_prior||0)+
       '" data-growth="'+(gp==null?-9999:gp)+'"><td class="rk">'+(i+1)+'</td>'+
       '<td class="nm">'+r.term+(r.niche?'<span class="niche">'+r.niche+'</span>':
         '<span class="newtag">no known niche</span>')+'</td>'+
       '<td class="num">'+num(r.clinics_now)+'</td><td class="num">'+num(r.clinics_prior)+'</td>'+
       '<td class="num g12">'+g+'</td><td class="l">'+(r.first_seen||'')+'</td>'+
       '<td class="l q">'+who+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>Adoption, not entry &mdash; and this is the gap everything else on the dashboard leaves open.</b><br>'+
    'Every other supply signal here is <b>name-mining</b>: it sees a company being incorporated, or a clinic being registered with CQC. But an <b>existing</b> clinic that starts offering a new service files nothing. It does not incorporate. It does not re-register. <b>It changes a page on its website.</b> That is invisible to every other tab &mdash; and it is plausibly how the ADHD boom actually spread: existing psychiatry and GP practices adding an assessment service, not founders incorporating "ADHD Ltd".<br>'+
    'So this tab watches a <b>fixed cohort</b> of real UK independent-healthcare clinic websites (taken from CQC\'s own directory, which publishes each location\'s website), walks them back through the <b>Internet Archive</b>, and counts how many <b>distinct clinics</b> now advertise a service that did not advertise it before. Rows tagged <span class="newtag">no known niche</span> come from an open vocabulary &mdash; a service nobody pre-listed.<br>'+
    '<b>Honest limits.</b> The cohort only contains CQC-registered clinics with a website, so sole-practitioner consultants &mdash; who may have been the actual first wave &mdash; are under-sampled. Blog posts are excluded (a page about ADHD is not the same as offering it). And the Archive\'s first sighting of a page is the date it <i>looked</i>, not the date the page appeared, so anything seen within three months of a site\'s first-ever capture is treated as pre-existing, never as a new adoption.</div>';
}

// Google's own RISING queries, harvested from broad seeds. This is the SEARCH-side open
// layer - the earliest place a niche nobody listed can appear, because it needs no
// company, no clinic and no prescription to exist. "Breakout" = >5000% growth.
function risingQ(){
  var Q=RADAR.topen||[];
  if(!Q.length)return '';
  var newOnes=Q.filter(function(r){return !r.niche;});
  var h='<h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:22px 0 8px">Rising Google searches nobody listed</h3>';
  if(!newOnes.length)return h+'<div class="msg">Every rising query maps to a niche we already track. That is a real result.</div>';
  h+='<table><thead><tr><th class="l">#</th><th class="l">Search term</th><th class="l">From seed</th>'+
     '<th class="l">Rise</th><th class="l">First seen</th></tr></thead><tbody>';
  newOnes.slice(0,25).forEach(function(r,i){
    var rise=(r.rise==='breakout')?'<span class="up">breakout</span>':
      '<span class="'+((r.rise_value||0)>=100?'up':'')+'">+'+num(r.rise)+'%</span>';
    h+='<tr><td class="rk">'+(i+1)+'</td><td class="nm">'+r.query+
       (r.is_new?' <span class="newtag">new</span>':'')+'</td><td class="l">'+(r.seed||'')+'</td>'+
       '<td class="l">'+rise+'</td><td class="l">'+(r.first_seen||'')+'</td></tr>';});
  return h+'</tbody></table><div class="note">Google\'s <b>rising related queries</b> for a rotating set of broad UK health seeds, filtered to the ones that map to <b>no niche we already track</b>. "Breakout" is Google\'s label for &gt;5000% growth. This is the earliest discovery surface on the dashboard: a search term needs no company, no clinic and no prescription in order to exist. It is also the noisiest &mdash; read it as a question.</div>';
}

// New UK medicine licences for large-population conditions.
function catTable(){
  var C=RADAR.cats||[];
  if(!C.length)return srcMsg('cats','No new large-population medicine licences in the window. Most of the register is rare oncology, which is stripped out.');
  var h='<table><thead><tr><th class="l">#</th><th class="l">Drug</th><th class="l">Condition</th>'+
    '<th class="l">Licensed</th><th class="l">Why it matters</th></tr></thead><tbody>';
  C.forEach(function(r,i){
    h+='<tr><td class="rk">'+(i+1)+'</td><td class="nm">'+r.name+
       (r.niche?'<span class="niche">'+r.niche+'</span>':'')+'</td>'+
       '<td class="l">'+(r.condition||'')+'</td><td class="l">'+(r.date||'')+'</td>'+
       '<td class="l q">'+(r.why||'')+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>The earliest and hardest signal on the dashboard.</b> New UK medicine licences (MHRA, via GOV.UK), filtered to <b>large-population conditions</b> &mdash; the rare-oncology long tail that dominates the register can never create a private-pay market and is stripped out.<br>'+
    'A licence lands <b>years</b> before the market. <b>Wegovy was licensed in Great Britain on 24 September 2021</b> &mdash; roughly 23 months before the UK weight-loss boom. Nothing else here could have seen that: no company had incorporated, no clinic had registered, nobody was searching for it, and it was not being prescribed.<br>'+
    '<b>What it CANNOT see:</b> ADHD. No new molecule created that boom &mdash; it was a diagnosis and awareness boom on old drugs. So this is a side panel, not a tier, and it never scores a niche.</div>';
}

// Rising DRUGS nobody put on a list. The same open-layer idea, applied to the whole
// NHS formulary: we already hold every chemical for every cached month, so ranking all
// of them by growth costs nothing extra. A new drug climbing fast is how the GLP-1
// market was created - and it is invisible to name-mining, because no new company or
// clinic has to exist for a GP to start prescribing something.
function drugDisc(){
  var D=RADAR.drugdisc||[];
  if(!D.length)return '';
  var h='<h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:22px 0 8px">Rising drugs nobody listed</h3>'+
    '<table><thead><tr><th class="l">#</th><th class="l">Chemical</th>'+
    '<th data-k="latest">Items / mo</th><th data-k="g3">3-mth</th><th data-k="g12">12-mth</th></tr></thead><tbody>';
  D.slice(0,20).forEach(function(r,i){
    h+='<tr data-latest="'+(r.latest||0)+'" data-g3="'+(r.g3==null?-9999:r.g3)+'" data-g12="'+(r.g12==null?-9999:r.g12)+
       '"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.name+'</td>'+
       '<td class="num">'+num(r.latest)+'</td><td class="num">'+fmt(r.g3)+'</td>'+
       '<td class="num g12">'+fmt(r.g12)+'</td></tr>';});
  return h+'</tbody></table><div class="note">Every BNF chemical in England, ranked by growth, with the ones already mapped to a known niche removed. This is the <b>drug-side open layer</b>: it can surface a treatment that is taking off before anyone has incorporated a company or registered a clinic to sell it. Most rows will be clinical noise (a reformulation, a supply shortage resolving). Read it as a question.</div>';
}

document.querySelectorAll('.panel').forEach(wireSort);

// ---- T4 prescribing: NHSBSA English Prescribing Dataset, fetched SERVER-side.
// 12 years of history (back to Jan 2014), no API key, ~2.5-month lag. We used to use
// OpenPrescribing, which serves only 60 months and 403s datacentre IPs - that 60-month
// window is why the ADHD boom (2021-23) was previously un-backtestable.
var PRESC = RADAR.presc||[];
document.getElementById('prbody').innerHTML=(PRESC.length?
  tableRows(PRESC,'Items / mo',{drug:true,firstCol:'Niche'}):srcMsg('presc','No prescribing rows.'))+
  '<div class="note"><b>T4 &middot; the latest tier, and the highest-confidence.</b> NHS items dispensed in England, from <b>NHSBSA\'s own open data</b> &mdash; 76 verified BNF chemical codes, 12 years of history, refreshed monthly (~2.5 months in arrears, not the 12+ we first assumed). '+
  '<b>Read T4 twice.</b> Prescribing can rise because the condition is genuinely growing &mdash; or because the NHS started FUNDING a treatment, which shrinks the private market for it. The data cannot separate those two, and neither can we. '+
  '9 niches have no valid NHS drug proxy at all (aesthetics, diagnostics, dental, tongue-tie, longevity, MSK, audiology, eye, private GP) and are marked <i>n/a</i>, never dashed.</div>';
wireSort(document.getElementById('pr'));

// ---- The Stack (T4 is now server-side, so no waiting on the browser) ----
document.getElementById('stbody').innerHTML=buildStack(PRESC);
wireSort(document.getElementById('st'));
</script></body></html>"""
