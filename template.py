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
&middot; read as a BUYER: proven demand + fragmented, tired supply &middot; click any column
to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="st">The Stack</div>
  <div class="tab" data-p="dc">Discovery</div>
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
<div class="panel" id="dc"><div id="dcbody"></div></div>
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
// ================================================================ THE TWO-AXIS READ
// Port of _agent2/interpret.py. Keep the constants in sync with that file.
//
// DEMAND  <- T0 NHS waits, T1 search.       Is there a market, and is it growing?
// SUPPLY  <- CQC standing population, T2, T3. Is there anything to BUY, and has
//                                             anyone already bought it?
//
// The old design read T1/T2/T3 as three independent confirmations of demand. They
// never were. T2 (new companies) and T3 (new clinics) are the SUPPLY RESPONSE. For a
// buyer they are not good news - they are competitors arriving and asking prices
// going up. Splitting the axes is the whole patch.
//
// T4 (NHS prescribing) votes on NOTHING. See the caveat text below.
var BOOM=40.0, FALLING=-10.0;
var MIN_TARGETS=30, THIN_TARGETS=100, TOP5_CONC=40.0, HHI_CONC=0.20;
// ENTRY RATE = new registrations in 12m / total standing stock. THE number for a
// buyer, and investability.py already computes both halves and throws the ratio away.
// These two cuts are the weakest-evidenced numbers in the whole dashboard - reasoned,
// not measured. Backtest these first.
var ENTRY_HOT=0.15, ENTRY_WARM=0.08;
// Niches where CQC structurally CANNOT see the supply. A botox/filler-only clinic is
// not carrying out a CQC-regulated activity, so it never registers. Reporting "no
// operators to buy" for aesthetics would be a lie told with a straight face.
// (Ideally this moves server-side into pull_and_build; it is here so this patch is
// self-contained.)
var CQC_BLIND={'Aesthetics / skin':1};

var QLABEL={
  buy_window:  'Buy — proven demand, owners still independent',
  wait_or_build:'Wait or build — new clinics still arriving',
  too_late:    'Too late — someone has already consolidated it',
  build_only:  'Build, not buy — there are no clinics to acquire',
  declining:   'Buy for cash only — demand is falling',
  nothing_here:'Nothing here yet',
  no_data:     'Not enough data to say'
};
var QELIG={buy_window:'buy',wait_or_build:'build',too_late:'neither',
           build_only:'build',declining:'buy',nothing_here:'neither',no_data:'neither'};
var QRANK={buy_window:0,wait_or_build:1,declining:2,build_only:3,too_late:4,
           nothing_here:5,no_data:6};
var QCLS={buy_window:'s3',wait_or_build:'s4',too_late:'s0',build_only:'s2',
          declining:'s4',nothing_here:'s1',no_data:'s1'};

function entryRate(iv){
  if(!iv)return null;
  var L=iv.locations,N=iv.new_12m;
  if(!L||N==null)return null;
  return N/L;
}
function readDemand(t0,t1,B){
  var b1=B.t1||{};
  var ind=b1.independent_items;
  // Every T1 term auto-discovered from T2/T3 => T1 is disqualified from voting.
  // Otherwise "T1 agrees with T2" is plumbing, not evidence.
  var u=(ind==null||ind>0)?t1:null;
  if(u==null&&t0==null)return 'unknown';
  if(u!=null&&u<=FALLING)return 'falling';
  if(u!=null&&u>=BOOM)return 'booming';
  if(fires(t0,B.t0)||fires(u,B.t1))return 'growing';
  return 'flat';
}
function readSupply(n,t2,t3,iv,B){
  if(!iv)return ['unknown',null];
  if(CQC_BLIND[n])return ['unobservable',entryRate(iv)];
  var indie=iv.indie_providers;
  if(indie==null)return ['unknown',entryRate(iv)];
  var er=entryRate(iv);
  if(indie<MIN_TARGETS)return ['none',er];
  var t5=iv.top5_share,hh=iv.hhi;
  if((t5!=null&&t5>=TOP5_CONC)||(hh!=null&&hh>=HHI_CONC))return ['consolidated',er];
  if(er!=null){if(er>=ENTRY_HOT)return ['filling',er];}
  else if(fires(t2,B.t2)&&fires(t3,B.t3))return ['filling',null];
  return ['fragmented',er];
}
function qscore(q,d,iv,er){
  if(q=='build_only')return d=='booming'?60:(d=='growing'?40:0);
  if(q!='buy_window'&&q!='declining')return 0;
  var indie=(iv||{}).indie_providers;
  if(indie==null)return 0;
  var density=100*Math.min(1,indie/(THIN_TARGETS*3));
  var h5=1-Math.min(1,((iv.top5_share||0)/TOP5_CONC));
  var hh=1-Math.min(1,((iv.hhi||0)/HHI_CONC));
  var headroom=100*Math.min(h5,hh);
  var cool=100*(1-Math.min(1,(er==null?ENTRY_WARM:er)/ENTRY_HOT));
  var s=0.40*density+0.35*headroom+0.25*cool;
  if(d=='falling')s*=0.5;          // buyable, but must not out-rank a live market
  else if(d=='booming')s*=0.9;     // you will pay for that growth
  return Math.round(s);
}
function qcaveats(q,sup,t1,t4,iv,B){
  var c=[];
  // ---- T4 is ambiguous. Always. State BOTH readings, assert neither.
  if(fires(t4,B.t4)){
    c.push('<b>NHS prescribing is up '+Math.round(t4)+'%, and this data cannot tell you '+
      'which of two opposite things that means.</b> Either the condition is growing '+
      '(your private market grows too), or the NHS has started FUNDING the treatment '+
      '(your private market is destroyed, because the patient can now get it free). '+
      'Check for NICE / NHS England guidance in the window before you read it either way.');
    if(t1!=null&&t1<=FALLING){
      c.push('<b>Warning:</b> NHS prescribing is rising while private search interest is '+
        'FALLING. That is exactly the pattern you would see if the NHS had taken the '+
        'patients. Suggestive, not proof — go and check.');
    }
  }
  // ---- T1 contamination
  var b1=B.t1||{},ind=b1.independent_items,it=b1.items;
  if(ind!=null&&it){
    if(ind===0)c.push('Every search term for this niche was <b>auto-discovered from the '+
      'supply tiers</b>, so T1 agreeing with T2/T3 proves nothing — it is the same '+
      'data twice. T1 has been excluded from the demand read.');
    else if(ind<it)c.push((it-ind)+' of '+it+' search terms here were auto-discovered '+
      'from T2/T3 and do not count toward conviction. '+ind+' independent term(s) remain.');
  }
  // ---- entry warming
  if(q=='buy_window'){
    var er=entryRate(iv);
    if(er!=null&&er>=ENTRY_WARM)c.push('Entry is warming ('+Math.round(er*100)+
      '% of the standing stock is new). Not a gold rush yet, but the window is '+
      'closing, not opening.');
    var ip=(iv||{}).indie_providers;
    if(ip!=null&&ip<THIN_TARGETS)c.push(ip+' independents is enough for a <b>regional '+
      'platform</b>, not a national consolidation. Size the ambition to the population.');
  }
  if(q=='build_only')c.push('<b>Building is a different business.</b> You carry the '+
    'demand risk yourself, there is no day-one cash flow, no seller to diligence, and '+
    'no multiple arbitrage — the whole return has to come from operating a startup.');
  if(q=='declining')c.push('A roll-up in a shrinking market earns its return from cost '+
    'synergies alone. Cash extraction, not buy-and-build: you would buy at 4x and sell '+
    'at 4x, and there is probably no trade buyer at the end.');
  if(sup=='unobservable')c.push('<b>CQC cannot see this niche.</b> Non-surgical '+
    'aesthetics is not a CQC-regulated activity, so those clinics never register. The '+
    'supply population is real but invisible — use the T2 Aesthetics tab as the '+
    'proxy and ignore the CQC columns here.');
  if(q=='buy_window'||q=='declining')c.push('A CQC Provider ID is a legal entity, not '+
    'an economic owner. A PE group holding twelve Ltds looks like twelve independents, '+
    'so fragmentation is systematically <b>over</b>stated.');
  return c;
}
function readNiche(n,t0,t1,t2,t3,t4,iv,B){
  var d=readDemand(t0,t1,B),s=readSupply(n,t2,t3,iv,B),sup=s[0],er=s[1];
  var q;
  if(sup=='unknown'||sup=='unobservable')q='no_data';
  else if(sup=='consolidated')q='too_late';       // beats everything: even booming
                                                  // demand is worthless if you are
                                                  // bidding against the consolidator
  else if(sup=='none')q=(d=='growing'||d=='booming')?'build_only':'nothing_here';
  else if(sup=='filling')q='wait_or_build';
  else if(d=='falling')q='declining';
  else q='buy_window';
  return {q:q,demand:d,supply:sup,er:er,label:QLABEL[q],elig:QELIG[q],
          rank:QRANK[q],cls:QCLS[q],score:qscore(q,d,iv,er),
          caveats:qcaveats(q,sup,t1,t4,iv,B)};
}
var DMCLS={booming:'dm-boom',growing:'dm-grow',flat:'dm-flat',falling:'dm-fall',
           unknown:'dm-unk'};
var SPCLS={fragmented:'sp-frag',filling:'sp-fill',consolidated:'sp-cons',
           none:'sp-none',unknown:'sp-unk',unobservable:'sp-unk'};
var SPTXT={fragmented:'fragmented',filling:'filling up',consolidated:'consolidated',
           none:'nothing to buy',unknown:'unknown',unobservable:'invisible to CQC'};
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
  var A0=aggB(RADAR.waits),
      A1=aggB(RADAR.trends,{index:true,independentOnly:true}),
      A2=aggB((RADAR.inc||[]).concat(RADAR.aes||[])),
      A3=aggB(RADAR.cqc),
      A4=aggB(presc);
  var IV=RADAR.invest||{};
  var names={};
  [A0.g,A1.g,A2.g,A3.g,A4.g].forEach(function(o){for(var k in o)names[k]=1;});
  for(var k in IV)names[k]=1;

  var rows=Object.keys(names).map(function(n){
    var B={t0:A0.b[n],t1:A1.b[n],t2:A2.b[n],t3:A3.b[n],t4:A4.b[n]};
    var r=readNiche(n,A0.g[n],A1.g[n],A2.g[n],A3.g[n],A4.g[n],IV[n],B);
    r.n=n;r.B=B;r.iv=IV[n];r.na4=NOPRESC.indexOf(n)>=0;
    r.t0=A0.g[n];r.t1=A1.g[n];r.t2=A2.g[n];r.t3=A3.g[n];r.t4=A4.g[n];
    return r;});

  // Buy targets first, then build ideas, then the dead ones. Within a group, by score.
  rows.sort(function(x,y){
    if(x.rank!==y.rank)return x.rank-y.rank;
    return y.score-x.score;});

  var h='<div class="chain"><b>Two questions, not one stage.</b> '+
    '<b>DEMAND</b> — is there a market, and is it growing, flat or rolling over? '+
    '(from T0 NHS waits and T1 search.) '+
    '<b>SUPPLY</b> — is there a population of clinics to BUY, and has anyone already '+
    'bought them? (from the CQC standing population, plus T2/T3 as the entry flow.)<br>'+
    'The valuable niche is <b>not the earliest</b>. It is <b>proven demand + a deep, '+
    'fragmented, tired owner population that new entrants have stopped joining</b>. '+
    'T2 (new companies) and T3 (new clinics) rising is <b>not good news for a buyer</b> '+
    '— it means competitors are multiplying and asking prices are going up.<br>'+
    '<b>Every niche is routed to one of your two businesses:</b> '+
    '<span class="el el-buy">buy</span> acquire clinics &middot; '+
    '<span class="el el-build">build</span> open one yourself — a different business '+
    'with a different risk profile &middot; '+
    '<span class="el el-neither">neither</span>.</div>';

  h+='<div class="warn"><b>Before you trust a cell.</b> Every percentage now carries the '+
    'two counts it was computed from. Where the base is under '+MIN_BASE+', <b>no '+
    'percentage is shown at all</b> — "+200%" on a base of 2 is two extra clinics, '+
    'and one extra clinic would have moved it 50 points. A number is only treated as '+
    '<b>firing</b> if it clears +'+RISING+'% <i>and</i> one standard deviation of counting '+
    'noise on its own base (±'+Math.round(noisePct(40))+'% at a base of 40, '+
    '±'+Math.round(noisePct(400))+'% at a base of 400). Percentages that clear +'+
    RISING+'% but sit inside their noise band are shown in <span class="na">grey</span>. '+
    'None of the thresholds is backtested — they are reasoning, not evidence, and the '+
    'two entry-rate cuts (' +Math.round(ENTRY_HOT*100)+'% / '+Math.round(ENTRY_WARM*100)+
    '%) are the weakest numbers here.</div>';

  if(RADAR.moved&&RADAR.moved.length){
    h+='<div class="mv"><b>What moved in the last 7 days</b> — note this panel is '+
       'still computed server-side on the OLD "early tiers agree" logic, which counts '+
       'T2/T3 (supply) as confirmation of demand. Read it as <i>"activity picked up"</i>, '+
       'not as <i>"this got more attractive to buy"</i>.<ul>';
    RADAR.moved.forEach(function(m){
      h+='<li>'+m.niche+' — activity now on <b>'+m.to+'</b> of 3 tiers (was '+
         m.from+' on '+m.since+')</li>';});
    h+='</ul></div>';
  }

  h+='<table><thead><tr><th class="l">#</th><th class="l">Niche</th>'+
     '<th data-k="t0">T0 NHS wait</th><th data-k="t1">T1 Search</th>'+
     '<th data-k="t2">T2 Companies</th><th data-k="t3">T3 Clinics</th>'+
     '<th data-k="t4">T4 Prescribing</th>'+
     '<th data-k="er">New sites</th><th class="l">Demand</th><th class="l">Supply</th>'+
     '<th data-k="score">Verdict</th><th class="l">For</th></tr></thead><tbody>';

  rows.forEach(function(r,i){
    var iv=r.iv||{};
    var erTxt=(r.er==null)?'<span class="na">&ndash;</span>'
      :('<span class="'+(r.er>=ENTRY_HOT?'dn':'')+'">'+Math.round(r.er*100)+'%</span>'+
        '<div class="den">'+num(iv.new_12m)+' of '+num(iv.locations)+'</div>');
    h+='<tr data-t0="'+(r.t0==null?-9999:r.t0)+'" data-t1="'+(r.t1==null?-9999:r.t1)+
       '" data-t2="'+(r.t2==null?-9999:r.t2)+'" data-t3="'+(r.t3==null?-9999:r.t3)+
       '" data-t4="'+(r.t4==null?-9999:r.t4)+
       '" data-er="'+(r.er==null?-9999:r.er)+'" data-score="'+r.score+'">'+
       '<td class="rk">'+(i+1)+'</td><td class="nm">'+r.n+'</td>'+
       '<td class="num">'+cellD(r.t0,r.B.t0)+'</td>'+
       '<td class="num">'+cellD(r.t1,r.B.t1)+'</td>'+
       '<td class="num">'+cellD(r.t2,r.B.t2)+'</td>'+
       '<td class="num">'+cellD(r.t3,r.B.t3)+'</td>'+
       '<td class="num">'+cellD(r.t4,r.B.t4,r.na4)+'</td>'+
       '<td class="num">'+erTxt+'</td>'+
       '<td class="l"><span class="dm '+DMCLS[r.demand]+'">'+r.demand+'</span></td>'+
       '<td class="l"><span class="sp '+SPCLS[r.supply]+'">'+SPTXT[r.supply]+'</span>'+
         (iv.indie_providers!=null?'<div class="den">'+num(iv.indie_providers)+
          ' indies</div>':'')+'</td>'+
       '<td class="l q"><span class="st '+r.cls+'">'+r.label+'</span></td>'+
       '<td class="l"><span class="el el-'+r.elig+'">'+r.elig+'</span></td></tr>';
    if(r.caveats.length){
      h+='<tr><td></td><td colspan="11">';
      r.caveats.forEach(function(c){h+='<div class="cav">'+c+'</div>';});
      h+='</td></tr>';
    }
  });

  h+='</tbody></table><div class="note"><b>New sites</b> is the number that matters most '+
     'and it is new: what share of the entire standing clinic population registered in '+
     'the last 12 months. High = a gold rush, every owner knows it, and you are bidding '+
     'against fresh entrants. Low = the rush is over, price competition has arrived, and '+
     'the owner who was turning patients away two years ago will take your call. '+
     '<b>The roll-up window opens when the boom ends but the demand does not.</b><br>'+
     'All growth figures are 12-month, pooled across every item mapped to that niche '+
     '(sum of the current counts over the sum of the year-ago counts). A dash = the '+
     'source has no reading (absent, not zero). T4 shows <i>n/a</i> where no NHS drug '+
     'proxy exists.</div>';
  return h;
}

document.getElementById('wtbody').innerHTML=(RADAR.waits&&RADAR.waits.length?
  tableRows(RADAR.waits,'Waiting',{firstCol:'NHS specialty'}):'<div class="msg">NHS RTT data unavailable this run.</div>')+
  '<div class="note"><b>T0 · the causal driver.</b> NHS England Referral-to-Treatment waits. Growth is measured on the <b>count waiting over 18 weeks</b> — deterioration in NHS access — not on total volume. When the NHS stops coping, patients go private; everything else on this dashboard is downstream of this. <b>Limits:</b> England only, ~6 weeks in arrears, consultant-led elective care only — so it is <b>blind to weight-loss and ADHD</b>, the two biggest private-pay niches. g1 is noisy (non-submitting trusts create fake swings); trust g3/g12.</div>';

document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term',index:true}):
  '<div class="msg">Search data appears after the next weekly run.</div>')+
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

document.getElementById('inbody').innerHTML=tableRows(RADAR.inc,'New (3m)',{firstCol:'Niche term'})+
  '<div class="note"><b>T2 · months.</b> Words rising fastest in the <b>names</b> of newly-incorporated health companies (9 SIC codes incl. 86210 general medical practice, where the ADHD/menopause/GLP-1 telehealth operators register). Incorporating is the cheapest possible bet on a niche, which is why it moves early.</div>'+
  ' <b>Read this as a WARNING, not a buy signal.</b> Every new company here is a future '+
  'competitor and a seller who has no reason to sell. Incorporating is the cheapest '+
  'possible bet on a niche (about £50), which is why it moves early — and why '+
  'it proves almost nothing. Blank growth = year-ago base under 3.';

document.getElementById('aebody').innerHTML=(RADAR.aes&&RADAR.aes.length?
  tableRows(RADAR.aes,'New (12m)',{firstCol:'Aesthetics keyword'}):'<div class="msg">Aesthetics miner returned nothing this run.</div>')+
  '<div class="note"><b>T2 · the CQC blind spot, closed.</b> Purely cosmetic treatment is <b>not</b> a CQC "regulated activity" — DHSC: <i>"TDDI does not include interventions carried out purely for cosmetic purposes."</i> So a botox/filler clinic needs no CQC registration and is <b>invisible to T3</b>. The Health and Care Act 2022 s.180 licensing scheme has <b>not commenced</b> — there is no register to read. Companies House is therefore the only national, dated record of an aesthetics business coming into existence. This tab mines 96 curated keywords (profhilo, polynucleotide, microneedling, HIFU, medispa…) across 8 SIC codes, whole-word matched. <b>Captures an estimated 20–35% of new aesthetics formation</b> (vs ~0% before); sole traders and mobile injectors — over half the entrants — remain unobservable. Read <i>latest</i> as a formation index, <b>not</b> a clinic count.</div>';

document.getElementById('cqbody').innerHTML=(RADAR.cqc&&RADAR.cqc.length?tableRows(RADAR.cqc,'New (12m)',{firstCol:'Clinic niche'}):'<div class="msg">No CQC data this run.</div>')+
  '<div class="note"><b>T3 · 6–18 months.</b> Locations newly registered with CQC, clustered by the words in their names. Scope: <b>Independent Healthcare</b> only. A clinic must register before it can legally trade, so this is committed capital. Counts are small (5–20 per niche) — a lead, not a measurement. See the Aesthetics tab for what this tier structurally cannot see.</div>'+
  ' <b>Also a warning, not a buy signal.</b> A new clinic registration is committed '+
  'capital arriving to compete with the assets you want to buy. On the Stack, T3 rising '+
  'is what pushes a niche into <i>"Wait or build — new clinics still arriving"</i>.';

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
   '<b>Two biases, both flattering:</b> (1) a Provider ID is a legal entity, not an economic owner &mdash; a PE-backed group holding twelve Ltds looks like twelve independents; (2) aesthetics is under-counted because non-surgical clinics are not CQC-registrable at all.</div>'+
  ' <b>What this tab still does not tell you:</b> whether the owners are TIRED. A '+
  'fragmented population of 500 clinics that all opened last year is not a roll-up — '+
  'it is a gold rush you would be bidding into. The <b>New sites</b> column on the Stack '+
  'is the fix: it divides the new registrations by the standing stock, and it is the '+
  'single most useful number on this dashboard for a buyer.';
}
document.getElementById('ivbody').innerHTML=ivTable();

function discTable(){
  var D=RADAR.disc||[];
  if(!D.length)return '<div class="msg">Nothing unclassified is rising fast enough to show. That is a real result, not a failure.</div>';
  var h='<table><thead><tr><th class="l">#</th><th class="l">Phrase</th>'+
    '<th data-k="ops">Distinct operators</th><th data-k="c12">Last 12m</th>'+
    '<th data-k="prior">Prior 12m</th><th data-k="growth">Growth</th>'+
    '<th class="l">First seen</th><th class="l">Seen in</th></tr></thead><tbody>';
  D.forEach(function(r,i){
    var g=(r.growth==null)?'<span class="na">&ndash;</span>':
      '<span class="'+(r.growth>=25?'up':'')+'">'+(r.growth>=0?'+':'')+Math.round(r.growth)+'%</span>';
    var tag=r.emerging?'<span class="newtag">emerging</span>':'';
    h+='<tr data-ops="'+(r.distinct_operators||0)+'" data-c12="'+(r.count_12m||0)+
       '" data-prior="'+(r.count_prior_12m||0)+'" data-growth="'+(r.growth==null?-9999:r.growth)+
       '"><td class="rk">'+(i+1)+'</td><td class="nm">'+r.phrase+' '+tag+'</td>'+
       '<td class="num">'+num(r.distinct_operators)+'</td>'+
       '<td class="num">'+num(r.count_12m)+'</td><td class="num">'+num(r.count_prior_12m)+'</td>'+
       '<td class="num g12">'+g+'</td><td class="l">'+(r.first_seen||'&ndash;')+'</td>'+
       '<td class="l">'+((r.sources||[]).join(', ')||'&ndash;')+'</td></tr>';});
  return h+'</tbody></table><div class="note"><b>The open layer &mdash; the only place a niche you have never heard of can appear.</b> '+
    'The other tabs re-rank 25 <i>pre-defined</i> niches; by construction they can never surface a new one. This tab is the <b>residue</b>: phrases mined from new company names and new clinic names that match <b>no</b> known niche.<br>'+
    '<b>How a brand is told apart from a niche:</b> a real service is used by many unrelated operators; a brand is used many times by one. So a phrase must appear across <b>&ge;6 distinct operators</b>, in <b>&ge;3 regions</b>, at &le;3 mentions per operator, and be rising. That kills brand names, franchises, surnames and place names structurally &mdash; not with a blocklist.<br>'+
    '<b>Read it as a question, not an answer.</b> These are unvetted strings. Most will be nothing. The point is that the machine is now able to be surprised.</div>';
}
document.getElementById('dcbody').innerHTML=discTable();

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
        '<div class="note"><b>T4 &middot; AMBIGUOUS. It votes on nothing, and here is why.</b> '+
    'NHS items dispensed in England (OpenPrescribing), 76 verified BNF codes batched into '+
    Object.keys(DRUGQ).length+' requests. Fetched live in your browser because '+
    'OpenPrescribing blocks datacentre IPs'+(p.length?'; latest month '+p[0].date:'')+'. '+
    '<b>Hover a row</b> for the drugs behind it.<br><br>'+
    '<b>Rising NHS prescribing has two opposite readings and this data cannot separate '+
    'them:</b><br>'+
    '&nbsp;&nbsp;<b>(a) the condition is growing.</b> More people have it, more people '+
    'want treating, and your private market grows alongside the NHS one. This is the '+
    'reading the old dashboard assumed, silently, by calling T4 a “maturity” '+
    'signal.<br>'+
    '&nbsp;&nbsp;<b>(b) the NHS has started FUNDING it.</b> The prescriptions rise '+
    '<i>because</i> the treatment became free at the point of use — and that '+
    '<b>destroys</b> your private clinic, because your entire proposition was that the '+
    'patient could not get it on the NHS. On this reading a rising T4 is a <b>SELL</b> '+
    'signal.<br><br>'+
    'We do not pretend to tell them apart. The <b>one</b> hint the data offers: if T4 is '+
    'rising while T1 (private search intent) is FALLING, that is the pattern you would '+
    'expect under (b) — and the Stack flags it. Suggestive, never proof. Go and check '+
    'whether NICE or NHS England issued guidance in the window.<br>'+
    '9 niches have no valid drug proxy and are marked <i>n/a</i>, not dashed — read '+
    'that as "not applicable", never "not yet".</div>';;
  wireSort(document.getElementById('pr'));
  document.getElementById('stbody').innerHTML=buildStack(p);
  wireSort(document.getElementById('st'));
}
loadPresc().then(finish).catch(function(){finish([]);});
</script></body></html>"""
