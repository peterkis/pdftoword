'use strict';
const $ = id => document.getElementById(id);
let token='', jobId='', data=null, layout=null, selected=null, operations=[];
let pageIndex=0, revision='auto', preview=false, unsavedPreview=false;
function message(error){$('error').textContent=error ? String(error.message || error) : '';}
async function api(path, body, form=false){
  const options=body===undefined ? {} : {method:'POST',headers:{'X-Demo-Session':token},body:form?body:JSON.stringify(body)};
  if(body!==undefined&&!form) options.headers['Content-Type']='application/json';
  const response=await fetch(path,options);
  const value=await response.json();
  if(!response.ok)throw new Error(value.detail||'请求失败');
  return value;
}
function on(id, fn){$(id).addEventListener('click',async()=>{message('');try{await fn();}catch(e){message(e);}});}
function asset(id){return '/api/asset/'+jobId+'/'+encodeURIComponent(id)+'?revision='+(preview?'preview':revision);}
function img(aid,cls){const el=document.createElement('img');el.src=asset(aid);el.className=cls;el.alt='源区域图片';return el;}
async function refresh(){const result=await api('/api/jobs');$('jobs').replaceChildren();for(const id of result.jobs){const o=document.createElement('option');o.value=id;o.textContent=id;$('jobs').append(o);}if(jobId)$('jobs').value=jobId;}
async function openJob(id){
  preview=false;unsavedPreview=false;jobId=id;data=await api('/api/job/'+id);operations=data.overrides.operations||[];
  revision=data.reviewed?'reviewed':'auto';$('revision').value=revision;
  layout=data[revision];pageIndex=layout.pages[0]?.page_index||0;
  $('pages').replaceChildren();for(const p of layout.pages){const o=document.createElement('option');o.value=p.page_index;o.textContent='源第 '+(p.page_index+1)+' 页';$('pages').append(o);}
  $('auto-download').href='/api/download/'+jobId+'/auto';
  $('reviewed-download').href=data.reviewed?'/api/download/'+jobId+'/reviewed':'';
  selected=null;$('blocks').hidden=false;$('rendered').hidden=true;$('rendered').replaceChildren();show();
}
function show(){
  if(!layout)return;
  const p=layout.pages.find(p=>p.page_index===pageIndex);
  $('source').src=asset('source-p'+pageIndex);$('overlay').setAttribute('viewBox',`0 0 ${p.width_pt} ${p.height_pt}`);
  $('blocks').replaceChildren();const byId=Object.fromEntries(p.blocks.map(b=>[b.id,b]));
  for(const id of p.reading_order){const b=byId[id];const el=document.createElement('article');el.className='block'+(selected?.id===id?' active':'');
    const label=document.createElement('small');label.textContent=b.id+' · '+b.type+' · '+b.geometry_source+' · '+b.render_policy;el.append(label);
    const parts=layout.metadata.inline_parts?.[b.id];
    if(b.content.kind==='image')el.append(img(b.content.asset_id,'figure'));
    else if(parts){for(const part of parts){el.append(part.omml?document.createTextNode('〔可编辑 Word 公式：'+part.latex+'〕'):part.asset_id?img(part.asset_id,'formula'):document.createTextNode(part.text));}}
    else el.append(document.createTextNode(b.content.plain_text||''));
    el.addEventListener('click',()=>choose(b));$('blocks').append(el);
  }
  $('issues').replaceChildren();for(const i of layout.issues.filter(i=>i.page_index===pageIndex)){
    const el=document.createElement('div');el.className='issue';el.textContent=i.id+' · '+i.type+' · '+i.status+' — '+i.message;
    if(i.block_ids.length){const b=document.createElement('button');b.textContent='定位';b.onclick=()=>{const found=p.blocks.find(x=>i.block_ids.includes(x.id));if(found)choose(found);};el.append(b);}
    if(i.status==='open'){const resolve=document.createElement('button');resolve.textContent='标记已核对';resolve.onclick=()=>operation({action:'resolve_issue',issue_id:i.id,page_index:i.page_index,block_id:i.block_ids[0]}).catch(e=>message(e));el.append(resolve);}
    $('issues').append(el);
  }
  $('alternatives').textContent=JSON.stringify({monkey:layout.provenance.monkey_geometry?.[pageIndex],ovis:layout.provenance.ovis_content?.[pageIndex]},null,2);
  $('operations').textContent=JSON.stringify(operations,null,2);
  const qa=revision==='reviewed'?data.qa_reviewed:data.qa;
  $('qa').textContent=qa?`主识别 ${layout.metadata.content_provider||layout.provenance.replay?.content_provider||"既有路径"} · 模型请求 ${qa.model_call_count} · 可编辑字符 ${qa.editable_text_char_count} · 图域 ${qa.placed_figure_count} · 原生公式 ${qa.omml_formula_count} · 公式图片 ${qa.formula_image_count} · ${qa.render_status} · 内容待人工审阅`: '待保存的人工修正预览';
}
function choose(b){
  selected=b;$('selected').textContent=b.id+' · 选中块的坐标来自 '+b.geometry_source+(b.flags.includes('text_geometry_unknown_full_page_reference')?' · 文字精确坐标未知，橙框仅表示整页来源':'');
  $('text').value=b.content.plain_text||b.content_candidates.find(c=>c.selected)?.text||'';
  $('bbox').value=b.bbox.map(x=>x.toFixed(2)).join(', ');$('policy').value=b.render_policy==='hybrid'?'review_required':b.render_policy;
  const [x,y,r,bt]=b.bbox;const scroll=$('source-wrap').parentElement;const page=layout.pages.find(p=>p.page_index===pageIndex);scroll.scrollTop=Math.max(0,y/page.height_pt*$('source-wrap').clientHeight-scroll.clientHeight/3);for(const [key,value] of Object.entries({x,y,width:r-x,height:bt-y}))$('region').setAttribute(key,value);
  $('candidate').replaceChildren();for(const c of b.content_candidates.filter(c=>c.provider==='ovis_ocr2'&&c.evidence?.review_selectable!==false)){const o=document.createElement('option');o.value=c.id;o.textContent=c.text;$('candidate').append(o);}
  $('target').replaceChildren();for(const p of layout.pages)for(const t of p.blocks.filter(t=>['question','figure','caption'].includes(t.type))){const o=document.createElement('option');o.value=t.id;o.textContent=t.id+' '+(t.content.plain_text||'图域').slice(0,45);$('target').append(o);}
  const original=data.auto.pages.flatMap(p=>p.blocks).find(x=>x.id===b.id);
  $('diff').textContent=JSON.stringify({automatic:original?.content,current:b.content,candidates:b.content_candidates,provenance:b.provenance_refs.map(r=>layout.provenance[r]),relations:layout.relations.filter(r=>r.from===b.id||r.to===b.id)},null,2);
  for(const e of $('blocks').children)e.classList.toggle('active',e.firstChild.textContent.startsWith(b.id+' ·'));
}
async function operation(op){
  if(!selected&&op.action!=='resolve_issue')throw new Error('请先选择一个块');
  if(!$('reason').value.trim())throw new Error('请填写操作原因，以保留修正来源');
  const next=[...operations,{block_id:selected?.id,reason:$('reason').value,...op}];
  const result=await api('/api/preview/'+jobId,{operations:next});operations=next;layout=result.layout;
  // Preview crops are registered in the preview revision served by backend.
  preview=true;unsavedPreview=true;revision='reviewed';data.reviewed=layout;data.qa_reviewed=null;$('revision').value=revision;
  const id=selected?.id;show();const b=layout.pages.flatMap(p=>p.blocks).find(b=>b.id===id);if(b)choose(b);
}
async function wait(){
  let s=await api('/api/status');$('status').textContent=s.state;
  while(s.busy){await new Promise(r=>setTimeout(r,800));s=await api('/api/status');$('status').textContent=s.state;}
  if(s.state==='失败')throw new Error(s.code||'任务失败');
  await refresh();if(s.job_id)await openJob(s.job_id);
}
on('replay',async()=>{await api('/api/replay',{content_provider:$('replay-provider').value});await wait();});on('refresh',refresh);
$('jobs').onchange=()=>openJob($('jobs').value).catch(message);
$('pages').onchange=()=>{pageIndex=Number($('pages').value);selected=null;show();};
$('revision').onchange=()=>{const next=$('revision').value;if(!data?.[next]){$('revision').value=revision;message('还未保存此版本');return;}revision=next;preview=revision==='reviewed'&&unsavedPreview;layout=data[revision];show();};
$('zoom').oninput=()=>{$('source-wrap').style.width=$('zoom').value+'%';};
$('upload').onsubmit=async event=>{event.preventDefault();message('');try{const form=new FormData($('upload'));for(const name of ['allow_model_calls','confirm_no_auth','confirm_scan','ovis','monkey'])form.set(name,$('upload').elements[name].checked?'true':'false');await api('/api/upload',form,true);await wait();}catch(e){message(e);}};
on('edit',()=>operation({action:'text',text:$('text').value}));
on('split',()=>operation({action:'split',offset:[...$('text').value.slice(0,$('text').selectionStart)].length}));on('merge',()=>operation({action:'merge'}));
on('up',()=>operation({action:'move',delta:-1}));on('down',()=>operation({action:'move',delta:1}));
on('crop',()=>operation({action:'crop',bbox:$('bbox').value.split(',').map(Number)}));
on('set-policy',()=>operation({action:'policy',policy:$('policy').value}));
on('relate',()=>operation({action:'relation',target_id:$('target').value,relation_type:$('relation-type').value}));
on('accept',()=>operation({action:'candidate',candidate_id:$('candidate').value}));
on('undo',async()=>{if(!operations.length)return;const next=operations.slice(0,-1);const result=await api('/api/preview/'+jobId,{operations:next});operations=next;layout=result.layout;preview=true;unsavedPreview=true;revision='reviewed';data.reviewed=layout;const id=selected?.id;show();selected=null;const b=layout.pages.flatMap(p=>p.blocks).find(b=>b.id===id);if(b)choose(b);else $('text').value='';});
on('save',async()=>{if(!jobId)throw new Error('请先选择任务');await api('/api/review/'+jobId,{operations});await openJob(jobId);$('status').textContent='已另存 reviewed.docx；auto 保持原样。';});
on('reconstruction',()=>{$('blocks').hidden=false;$('rendered').hidden=true;});
on('render',async()=>{if(!jobId)return;if(preview)throw new Error('请先保存修正，再渲染 reviewed.docx');const requested=revision;await api('/api/render/'+jobId,{revision});await wait();revision=requested;$('revision').value=revision;layout=data[revision];show();const qa=revision==='auto'?data.qa:data.qa_reviewed;$('rendered').replaceChildren();$('blocks').hidden=true;$('rendered').hidden=false;if(qa?.render_status!=='RENDERED'){$('rendered').textContent='DOCX_VISUAL_REVIEW_PENDING：请下载 DOCX，在本机 Word 打开检查。';return;}for(let n=1;n<=qa.rendered_page_count;n++)$('rendered').append(img('render-'+n,''));});
let drag=null;
function point(event){const rect=$('overlay').getBoundingClientRect();const p=layout.pages.find(p=>p.page_index===pageIndex);return [(event.clientX-rect.left)/rect.width*p.width_pt,(event.clientY-rect.top)/rect.height*p.height_pt];}
$('overlay').onpointerdown=e=>{if(!selected)return;drag=point(e);$('overlay').setPointerCapture(e.pointerId);};
$('overlay').onpointermove=e=>{if(!drag)return;const end=point(e);const b=[Math.min(drag[0],end[0]),Math.min(drag[1],end[1]),Math.max(drag[0],end[0]),Math.max(drag[1],end[1])];$('bbox').value=b.map(n=>n.toFixed(2)).join(', ');for(const [k,v] of Object.entries({x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1]}))$('region').setAttribute(k,v);};
$('overlay').onpointerup=()=>{drag=null;};
(async()=>{const session=await api('/api/session');token=session.token;await refresh();if($('jobs').value)await openJob($('jobs').value);})().catch(message);
