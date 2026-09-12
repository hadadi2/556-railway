/* Optional UI; failures stay inside the opportunity panel. No chart estimates. */
window.SilkOpportunities = (() => {
  let enabled=false, epoch=0, current=null, saved=[], products=[], identity=null, page=1, archived=false, pageData={summary:{}}, searchEpoch=0;
  const text=(ar,en)=>ar_en(ar,en), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const call=(path='',options)=>api('/export-opportunities'+path,options);
  const post=(path,body)=>call(path,{method:'POST',body:JSON.stringify(body)});
  // Keep decision figures in Latin digits in both interfaces. Currency values
  // carry their unit beside every figure so the table remains clear in RTL.
  const number=v=>v==null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(v);
  const money=v=>v==null?'—':'<bdi dir="ltr">USD '+number(v)+'</bdi>';
  const marketName=o=>(LANG==='ar'&&o.snapshot?.row?.item?.name_ar)||o.market_name;
  const date=v=>v?new Date(v).toLocaleString(LANG==='ar'?'ar-SA':'en-US'):'—';
  const state=s=>({draft:text('مسودة دراسة','Study draft'),in_progress:text('الدراسة قيد الإعداد','Study in progress'),completed:text('الدراسة مكتملة','Study completed'),archived:text('مؤرشفة','Archived'),cancelled:text('ملغاة','Cancelled')})[s]||s||text('محفوظة','Saved');
  const error=(node,e)=>{node.innerHTML='<p class="eperror" role="alert">'+esc(e.message||text('تعذر التحميل، أعد المحاولة.','Unable to load; please retry.'))+'</p>';};
  async function configure(){
    const turn=++epoch;
    enabled=false; current=null; saved=[]; products=[]; identity=ME?.user_id||ME?.email;
    try{const d=await call('/config',{signal:AbortSignal.timeout(5000)});if(turn===epoch)enabled=!!d.enabled;}catch(_){/* optional */}
  }
  function card(label,value){return '<div class="epcard"><span class="eplabel">'+esc(label)+'</span><b>'+esc(value)+'</b></div>';}
  async function openStudies(id){const who=identity;await loadAll();if(who!==identity)return;STUDY_FILTER.q='';STUDY_FILTER.state='all';SELECTED_STUDY=String(id);showSection('studies');renderStudyRows();}
  async function render(key){
    if(!enabled||!['opportunities','opportunity_metrics'].includes(key))return;
    const node=document.getElementById(key==='opportunity_metrics'?'opportunityMetricsPanel':'opportunitiesPanel'), turn=++epoch;
    node.innerHTML='<p role="status">'+text('جارٍ التحميل…','Loading…')+'</p>';
    try{
      if(ME.role==='silk_admin'){await admin(node,turn);return;}
      const result=await Promise.all([api('/products'),call('?page='+page+'&archived='+archived)]);
      if(turn!==epoch)return;
      products=result[0].products; pageData=result[1];page=pageData.page;saved=pageData.opportunities; current=null;
      node.innerHTML='<div class="epintro"><div><h2>'+text('من السوق المناسب إلى دراسة واضحة','From market opportunity to a clear study')+'</h2><p class="epsub">'+text('اكتشف فرص منتجك، احفظ السوق، ثم ابدأ دراسة ملاءمته لمصنعك.','Explore product opportunities, save a market, then study its fit for your factory.')+'</p></div></div>'+
        '<div class="eptrack">'+text('١ استكشف الأسواق　←　٢ احفظ الفرصة　←　٣ راجع المنتج والسوق　←　٤ أنشئ مسودة دراسة','1 Explore markets → 2 Save opportunity → 3 Review product and market → 4 Create study draft')+'</div>'+
        '<div class="epcards" id="oppKpis">'+card(text('فرصي المحفوظة','Saved opportunities'),number(pageData.summary.total||0))+card(text('فرص مرتبطة بدراسة','Linked to studies'),number(pageData.summary.linked||0))+card(text('دراسات مكتملة','Completed studies'),number(pageData.summary.completed||0))+'</div>'+
        '<div class="epfilters"><label>'+text('منتج المصنع','Factory product')+'<select id="oppProduct"><option value="">'+text('اختر منتجًا من كتالوجك','Choose a catalog product')+'</option>'+products.map(p=>'<option value="'+p.id+'">'+esc(p.name)+' · '+esc(p.hs_code||text('الرمز غير مكتمل','Code missing'))+'</option>').join('')+'</select></label><div><span class="eplabel">'+text('بلد التصدير','Exporting country')+'</span><b>'+text('السعودية','Saudi Arabia')+'</b></div><button class="btn" id="oppExplore">'+text('استكشف الأسواق','Explore markets')+'</button><button class="btn gh" id="oppProducts">'+text('إدارة المنتجات','Manage products')+'</button></div>'+
        '<p class="epsub">'+text('يلزم رمز منتج محدد من ٦ أرقام. ربط الدراسة في هذا الإصدار للصادرات السعودية.','A specific six-digit product code is required. Study integration in this version covers Saudi exports.')+'</p><div id="oppMarkets"></div><div id="oppStudyForm"></div><div class="epsection"><h3>'+text('فرصي المحفوظة','My saved opportunities')+'</h3><div id="oppSaved"></div></div>';
      document.getElementById('oppProducts').onclick=()=>showSection('products');
      document.getElementById('oppExplore').onclick=explore;
      document.getElementById('oppProduct').onchange=()=>{searchEpoch++;current=null;document.getElementById('oppMarkets').textContent='';};
      renderSaved();
    }catch(e){if(turn===epoch)error(node,e);}
  }
  async function explore(){
    const node=document.getElementById('oppMarkets'), pid=Number(document.getElementById('oppProduct').value), turn=epoch, requestId=++searchEpoch;
    const p=products.find(x=>x.id===pid); current=null;
    if(!p||!/^\d{6}$/.test(p.hs_code||'')){error(node,new Error(text('اختر منتجًا له رمز صحيح من ستة أرقام؛ يمكنك استكماله في المنتجات.','Choose a product with a six-digit code; update it in Products.')));return;}
    const btn=document.getElementById('oppExplore');btn.disabled=true;node.innerHTML='<p role="status">'+text('جارٍ جلب بيانات ITC…','Retrieving ITC data…')+'</p>';
    try{
      const d=await call('/markets?product_id='+pid+'&exporter=682');
      if(turn!==epoch||requestId!==searchEpoch||Number(document.getElementById('oppProduct').value)!==pid)return;
      current=d;
      const allRows=d.rows.filter(r=>r.id!=='682').sort((a,b)=>(b.potential??-1)-(a.potential??-1)), rows=allRows.slice(0,20), max=Math.max(1,...rows.map(r=>r.potential||0));
      node.innerHTML='<h3>'+text('أعلى الأسواق حسب إمكانات ITC','Top markets by ITC export potential')+'</h3><p class="epnotice">'+text('إمكانات التجارة بين الدول، وليست إيرادات متوقعة لمصنعك. الأرقام بالدولار الأمريكي.','Country-to-country trade potential, not expected factory revenue. Values in USD.')+'</p><div class="epstamp">ITC Export Potential Map · '+text('فترة التجارة: ','Trade period: ')+esc(d.period.trade_years||'—')+' · '+text('تقديرات عام ','Projection year ')+esc(d.period.target_year||'—')+' · '+text('آخر جلب: ','Retrieved: ')+esc(date(d.provenance.retrieved_at))+'</div>'+
      (rows.length?'<div class="eptable"><table><thead><tr><th>'+text('السوق','Market')+'</th><th>'+text('إمكانات التصدير (USD)','Export potential (USD)')+'</th><th>'+text('غير المستغل (USD)','Unrealized (USD)')+'</th><th></th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+esc(r.item.name_ar&&LANG==='ar'?r.item.name_ar:r.item.name)+'</td><td>'+money(r.potential)+'<div class="epbar"><i style="width:'+Math.max(0,Math.min(100,(r.potential||0)/max*100))+'%"></i></div></td><td class="epgap">'+money(r.unrealized)+'</td><td><button class="btn gh sm" data-save="'+esc(r.id)+'">'+text('احفظ الفرصة','Save opportunity')+'</button></td></tr>').join('')+'</tbody></table></div>':'<p class="epempty">'+text('لا توجد نتائج لهذا المنتج لدى ITC.','ITC has no results for this product.')+'</p>')+
      '<p><a class="btn gh" href="/export-potential?axis=markets&exporter=682&product='+encodeURIComponent(d.product.hs_code)+'&market=w&to=j&what=k" target="_blank" rel="noopener">'+text('عرض الرسوم وجميع الأسواق ↗','View charts and all markets ↗')+'</a></p>';
      const searchInput=document.createElement('input');searchInput.type='search';searchInput.placeholder=text('ابحث في جميع الأسواق المسترجعة…','Search all retrieved markets…');searchInput.setAttribute('aria-label',searchInput.placeholder);searchInput.className='opp-market-search';
      const table=node.querySelector('table');
      if(table){table.parentElement.before(searchInput);searchInput.oninput=()=>{const q=searchInput.value.trim().toLowerCase();const filtered=allRows.filter(r=>[r.id,r.item.name,r.item.name_ar].join(' ').toLowerCase().includes(q)).slice(0,20);table.querySelector('tbody').innerHTML=filtered.map(r=>'<tr><td>'+esc(LANG==='ar'&&r.item.name_ar?r.item.name_ar:r.item.name)+'</td><td>'+money(r.potential)+'</td><td>'+money(r.unrealized)+'</td><td><button class="btn gh sm" data-save="'+esc(r.id)+'">'+text('احفظ الفرصة','Save opportunity')+'</button></td></tr>').join('');table.querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>save(b,d));};}
      node.querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>save(b,d));
    }catch(e){if(turn===epoch&&requestId===searchEpoch)error(node,e);}finally{btn.disabled=false;}
  }
  async function save(btn,d){
    btn.disabled=true;const turn=epoch;
    try{await post('',{product_id:d.product.id,exporter:'682',market:btn.dataset.save,response_sha256:d.provenance.response_sha256});const result=await call('?page='+page+'&archived='+archived);if(turn!==epoch)return;pageData=result;page=result.page;saved=result.opportunities;renderSaved();btn.textContent=text('محفوظة ✓','Saved ✓');}
    catch(e){if(turn===epoch)error(document.getElementById('oppStudyForm'),e);btn.disabled=false;}
  }
  function renderSaved(){
    const node=document.getElementById('oppSaved');
    document.getElementById('oppKpis').innerHTML=card(text('فرصي المحفوظة','Saved opportunities'),number(pageData.summary.total||0))+card(text('فرص مرتبطة بدراسة','Linked to studies'),number(pageData.summary.linked||0))+card(text('دراسات مكتملة','Completed studies'),number(pageData.summary.completed||0));
    node.innerHTML=saved.length?'<p class="epnotice">'+text('الخطوة التالية: اضغط «ابدأ دراسة السوق»، راجع بيانات المنتج والسوق، ثم أنشئ المسودة وأطلقها من قسم الدراسات.','Next: select Start market study, review the product and market, create the draft, then launch it from Studies.')+'</p><div class="eptable"><table><thead><tr><th>'+text('المنتج / السوق','Product / market')+'</th><th>'+text('لقطة إمكانات ITC (USD)','ITC potential snapshot (USD)')+'</th><th>'+text('الحالة','Status')+'</th><th>'+text('الخطوة التالية','Next step')+'</th></tr></thead><tbody>'+saved.map(o=>'<tr><td>'+esc(o.snapshot.product_name)+'<br><small>'+esc(marketName(o))+' · '+esc(o.hs_code)+'</small></td><td>'+money(o.snapshot.row.potential)+'<br><small>'+esc(date(o.snapshot.provenance.retrieved_at))+'</small></td><td>'+esc(o.link_status==='changed'?text('تغير نطاق الدراسة','Study scope changed'):state(o.study_state))+'</td><td><button class="btn gh sm" data-study="'+o.id+'">'+(o.study_state?text('الدراسة #','Study #')+o.study_id:text('ابدأ دراسة السوق','Start market study'))+'</button> <button class="btn gh sm" data-archive="'+o.id+'">'+(archived?text('استعادة','Restore'):text('أرشفة','Archive'))+'</button></td></tr>').join('')+'</tbody></table></div>':'<p class="epempty">'+text('ابدأ باستكشاف أحد منتجاتك، ثم احفظ السوق الذي يهمك.','Explore a product, then save a market that interests you.')+'</p>';
    node.insertAdjacentHTML('beforeend','<div class="eprowbtns"><button class="btn gh" id="oppArchiveView">'+(archived?text('الفرص النشطة','Active opportunities'):text('الأرشيف','Archive'))+'</button><button class="btn gh" id="oppPrev" '+(page<=1?'disabled':'')+'>'+text('السابق','Previous')+'</button><span>'+number(page)+' / '+number(Math.max(1,Math.ceil(pageData.total/pageData.page_size)))+'</span><button class="btn gh" id="oppNext" '+(page*pageData.page_size>=pageData.total?'disabled':'')+'>'+text('التالي','Next')+'</button></div>');
    const refresh=async()=>{const turn=epoch;try{const d=await call('?page='+page+'&archived='+archived);if(turn!==epoch)return;pageData=d;page=d.page;saved=d.opportunities;renderSaved();}catch(e){if(turn===epoch)error(node,e);}};
    document.getElementById('oppArchiveView').onclick=()=>{archived=!archived;page=1;refresh();};
    document.getElementById('oppPrev').onclick=()=>{page--;refresh();};
    document.getElementById('oppNext').onclick=()=>{page++;refresh();};
    node.querySelectorAll('[data-archive]').forEach(b=>b.onclick=async()=>{const turn=epoch;b.disabled=true;try{await post('/'+b.dataset.archive+'/archive',{archived:!archived});if(turn===epoch)await refresh();}catch(e){if(turn===epoch)error(node,e);}});
    node.querySelectorAll('[data-study]').forEach(b=>b.onclick=()=>{const o=saved.find(x=>x.id===Number(b.dataset.study));if(o.study_state)openStudies(o.study_id);else if(!archived)form(o);});
  }
  function form(o){
    const node=document.getElementById('oppStudyForm'), p=products.find(x=>x.id===o.product_id);
    node.innerHTML='<div class="epform"><h3>'+text('مراجعة نطاق دراسة السوق','Review study scope')+'</h3><p>'+esc(o.snapshot.product_name)+' · '+esc(marketName(o))+' · '+esc(o.hs_code)+'</p><p class="epsub">'+text('تراجع الدراسة الطلب والمنافسة ومتطلبات الدخول والجدوى وفق المصادر المتاحة. المعلومات الناقصة تبقى معلنة.','The study reviews demand, competition, entry requirements and feasibility using available sources. Missing information remains explicit.')+'</p><p>'+text('لتحسين الدراسة: استكمل الطاقة الإنتاجية وتكلفة الوحدة والشهادات في بطاقة المنتج.','For a better study, complete capacity, unit cost and certifications in the product card.')+'</p><div class="eprowbtns"><button class="btn gh" id="oppEditProduct">'+text('راجع بيانات المنتج','Review product details')+'</button></div><label>'+text('هدف الدراسة وملاحظات المصنع','Study objective and factory notes')+'<textarea id="oppNotes" maxlength="2000"></textarea></label><label class="epconfirm"><input id="oppConfirm" type="checkbox"><span>'+text('راجعت أن المنتج ورمزه والسوق المختار مناسبة لنطاق دراستي. هذا لا يغني عن تحقق تصنيف المنتج داخل الدراسة.','I reviewed the product, code and target market for my study scope. This does not replace product classification validation within the study.')+'</span></label><p class="epnotice">'+text('سيتم إنشاء مسودة فقط. الإطلاق من قسم الدراسات يستهلك حصة من باقتك وفق الإجراءات الحالية.','Only a draft will be created. Launching from Studies consumes your plan quota through the existing process.')+'</p><button class="btn" id="oppCreateDraft">'+text('أنشئ مسودة الدراسة','Create study draft')+'</button><div id="oppDraftMessage" role="status"></div></div>';
    document.getElementById('oppEditProduct').onclick=()=>showSection('products');
    document.getElementById('oppCreateDraft').onclick=async function(){
      const msg=document.getElementById('oppDraftMessage');if(!document.getElementById('oppConfirm').checked){msg.textContent=text('راجع الاختيار وأكّد النطاق أولًا.','Review and confirm the scope first.');return;}
      this.disabled=true;const turn=epoch;
      try{const d=await post('/'+o.id+'/study',{confirmed:true,notes:document.getElementById('oppNotes').value});if(turn!==epoch)return;msg.innerHTML='<p>'+text('أُنشئت مسودة الدراسة #','Study draft created #')+d.study_id+'</p><button class="btn gh" id="oppGoStudy">'+text('افتح قسم الدراسات للمراجعة والإطلاق','Open Studies to review and launch')+'</button>';document.getElementById('oppGoStudy').onclick=()=>openStudies(d.study_id);const list=await call('?page='+page+'&archived='+archived);if(turn===epoch){pageData=list;saved=list.opportunities;renderSaved();}}
      catch(e){if(turn===epoch){error(msg,e);this.disabled=false;}}
    };
    node.scrollIntoView({behavior:'smooth',block:'start'});
  }
  async function admin(node,turn,days=30){
    const d=await call('/admin/metrics?days='+days);if(turn!==epoch)return;
    const f=d.public_funnel||{};
    node.innerHTML='<div class="epintro"><div><h2>'+text('أداء فرص التصدير','Export opportunities performance')+'</h2><p class="epsub">'+text('مؤشرات استخدام وتشغيل مجمعة؛ لا تمثل صفقات أو إيرادات.','Aggregated usage and operations, not deals or revenue.')+'</p></div><select id="oppDays">'+[7,30,90].map(n=>'<option value="'+n+'" '+(n===days?'selected':'')+'>'+text('آخر '+n+' يومًا','Last '+n+' days')+'</option>').join('')+'</select><button class="btn gh" id="oppMetricsRefresh">'+text('تحديث','Refresh')+'</button></div><h3>'+text('تحويل زوار صفحة الهبوط','Landing visitor funnel')+'</h3><div class="epcards">'+card(text('بدأوا البحث','Searches started'),number(f.search_started||0))+card(text('شاهدوا أفضل الأسواق','Previews shown'),number(f.preview_shown||0))+card(text('ضغطوا كشف الأرقام','Reveal clicks'),number(f.signup_clicked||0))+card(text('دخلوا إلى حسابهم','Signed-in returns'),number(f.login_completed||0))+card(text('انتقلوا للاشتراك','Subscription clicks'),number(f.subscription_clicked||0))+'</div><h3>'+text('استخدام المصانع','Factory usage')+'</h3><div class="epcards">'+card(text('مصانع استخدمت الوحدة','Factories using the module'),number(d.active_factories))+card(text('فرص حُفظت خلال الفترة','Opportunities saved in period'),number(d.events.saved||0))+card(text('مسودات طُلبت خلال الفترة','Drafts requested in period'),number(d.events.study_requested||0))+card(text('أخطاء جلب خلال الفترة','Source errors in period'),number(d.events.source_error||0))+'</div><h3>'+text('حالة الدراسات المطلوبة خلال الفترة','Status of studies requested in this period')+'</h3><div class="epcards">'+Object.entries(d.study_states).map(([k,v])=>card(state(k),number(v))).join('')+'</div>'+(!Object.keys(d.study_states).length?'<p class="epempty">'+text('لا توجد دراسات مرتبطة بعد.','No linked studies yet.')+'</p>':'')+'<h3>'+text('الأسواق الأكثر حفظًا خلال الفترة','Most saved markets in period')+'</h3><div class="eptable"><table><tbody>'+d.top_markets.map(r=>'<tr><td>'+esc(LANG==='ar'&&r.market_name_ar?r.market_name_ar:r.market_name)+'</td><td>'+number(r.n)+'</td></tr>').join('')+'</tbody></table></div><h3>'+text('متابعة مصدر البيانات','Data source monitoring')+'</h3><div class="eptrack">'+text('آخر طلب بيانات ناجح: ','Last successful data request: ')+esc(date(d.source.last_success_at))+'<br>'+text('آخر طلب بيانات فاشل: ','Last failed data request: ')+esc(date(d.source.last_failure_at))+'</div><p class="epstamp">'+text('هذه تواريخ طلبات الوحدة وليست تاريخ إصدار بيانات التجارة. لا توجد مراقبة تلقائية في الخلفية.','These are module request timestamps, not trade release dates. No background monitoring is running.')+'</p>';
    const reload=()=>{const selected=Number(document.getElementById('oppDays').value);node.innerHTML='<p>'+text('جارٍ التحديث…','Refreshing…')+'</p>';const turn=++epoch;admin(node,turn,selected).catch(e=>{if(turn===epoch)error(node,e);});};
    document.getElementById('oppDays').onchange=reload;document.getElementById('oppMetricsRefresh').onclick=reload;
  }
  async function openProduct(pid){
    await render('opportunities');
    const select=document.getElementById('oppProduct');
    if(!select||!products.some(p=>p.id===pid))return false;
    select.value=String(pid);await explore();return true;
  }
  return {configure,render,openProduct,reset:()=>{enabled=false;epoch++;searchEpoch++;identity=null;current=null;saved=[];products=[];page=1;archived=false;},isEnabled:()=>enabled,invalidate:()=>{epoch++;}};
})();

