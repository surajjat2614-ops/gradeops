<<<<<<< HEAD
const escapeHtml = (unsafe) => (unsafe ?? '').toString().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
// ─── State ───
let sessionId=null,extractedQuestions=[],coordMap={},currentSelection=null,activeCanvasKind="question",isDragging=false,startPoint=null;
const qImg=new Image(),aImg=new Image();
let dashData=null,reviewQueue=[],allResults=[],rIdx=0;
let reviewStatuses={};
let pipelineTimerInterval=null,pipelineStartTime=null;

// ─── DOM refs ───
const navItems=document.querySelectorAll('.nav-item'),views=document.querySelectorAll('.view-section');
const qCanvas=document.getElementById("questionCanvas"),qCtx=qCanvas?.getContext("2d");
const aCanvas=document.getElementById("answerCanvas"),aCtx=aCanvas?.getContext("2d");

// ─── Helpers ───
function notify(msg,type='info'){
  if (typeof msg === 'object') { msg = JSON.stringify(msg); }
  const c=document.getElementById('notificationContainer');if(!c)return;
  const e=document.createElement('div');
  e.className=`notification ${escapeHtml(type)}`;
  const iconIds={success:'ico-check',error:'ico-x',warning:'ico-alert',info:'ico-info'};
  e.innerHTML=`<svg class="icon icon-sm"><use href="#${iconIds[type]||'ico-info'}"/></svg><span>${escapeHtml(msg)}</span>`;
  c.appendChild(e);
  setTimeout(()=>{e.style.opacity='0';e.style.transform='translateY(-10px)';e.style.transition='all .3s';setTimeout(()=>e.remove(),300)},3500);
}
function updateFileName(input,labelId,multi=false){
  const l=document.getElementById(labelId);if(!l)return;
  if(input.files?.length){l.classList.remove('hidden');l.textContent=multi?`${escapeHtml(input.files.length)} files`:input.files[0].name}
  else l.classList.add('hidden');
}

// ─── Navigation ───
function switchView(id){
  navItems.forEach(n=>{n.classList.toggle('active',n.dataset.target===id)});
  views.forEach(v=>{
    const show=v.id===id;
    v.classList.toggle('hidden',!show);
    if(show){v.classList.remove('view-entering');void v.offsetWidth;v.classList.add('view-entering');staggerChildren(v)}
  });
  if(id==='view-rubrics'){populateRubricQuestionPicker();loadSavedRubrics()}
  if(id==='view-students'){renderStudentReports()}
  updateTabTitle(id);
}
navItems.forEach(n=>n.addEventListener('click',()=>switchView(n.dataset.target)));
function markStep(id,done){document.getElementById(id)?.classList.toggle('completed',done)}

// ─── Upload ───
document.getElementById('uploadForm')?.addEventListener('submit',async e=>{
  e.preventDefault();const btn=document.getElementById('btn-upload');btn.textContent='Uploading…';btn.disabled=true;
  try{
    const r=await fetch("/api/exams/upload",{method:"POST",body:new FormData(e.target)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    sessionId=d.session_id;extractedQuestions=d.questions||[];coordMap={};
    notify('Upload successful!','success');markStep('nav-upload',true);
    document.getElementById('uploadResultContainer').classList.remove('hidden');
    document.getElementById('uploadResult').textContent=`Session: ${escapeHtml(sessionId)}`;
    renderQPicker();renderQList();populateRubricQuestionPicker();
    setTimeout(()=>switchView('view-crop'),1200);
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Upload & Create Session';btn.disabled=false}
});

// ─── Cropping ───
function setCropTab(kind){
  if(kind==='answer'&&!extractedQuestions.length){notify('Extract at least one question first.','warning');return}
  activeCanvasKind=kind;
  document.getElementById('questionTabPanel').classList.toggle('hidden',kind!=='question');
  document.getElementById('answerTabPanel').classList.toggle('hidden',kind!=='answer');
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',i===(kind==='question'?0:1)));
  currentSelection=null;drawPreview();
}
document.getElementById('tabQuestions')?.addEventListener('click',()=>setCropTab('question'));
document.getElementById('tabAnswers')?.addEventListener('click',()=>setCropTab('answer'));

function gc(){return activeCanvasKind==='question'?qCanvas:aCanvas}
function gx(){return activeCanvasKind==='question'?qCtx:aCtx}
function gi(){return activeCanvasKind==='question'?qImg:aImg}

function drawPreview(){
  const c=gc(),x=gx(),img=gi();if(!img.src||!c||!x)return;
  x.clearRect(0,0,c.width,c.height);x.drawImage(img,0,0,c.width,c.height);
  if(currentSelection){
    x.fillStyle='rgba(0,0,0,0.45)';
    x.beginPath();
    x.rect(0, 0, c.width, c.height);
    x.rect(currentSelection.x, currentSelection.y, currentSelection.w, currentSelection.h);
    x.fill('evenodd');
    
    x.strokeStyle='#818cf8';x.lineWidth=2;
    x.strokeRect(currentSelection.x,currentSelection.y,currentSelection.w,currentSelection.h);
    
    x.fillStyle='#fff';const s=6,{x:sx,y:sy,w:sw,h:sh}=currentSelection;
    [[sx,sy],[sx+sw/2,sy],[sx+sw,sy],[sx,sy+sh/2],[sx+sw,sy+sh/2],[sx,sy+sh],[sx+sw/2,sy+sh],[sx+sw,sy+sh]]
      .forEach(p=>x.fillRect(p[0]-s/2,p[1]-s/2,s,s));
  }
}

function c2o(sel){const c=gc(),img=gi(),sx=img.naturalWidth/c.width,sy=img.naturalHeight/c.height;
  return{x:Math.max(0,Math.round(sel.x*sx)),y:Math.max(0,Math.round(sel.y*sy)),w:Math.max(1,Math.round(sel.w*sx)),h:Math.max(1,Math.round(sel.h*sy))}}

function renderQPicker(){
  const p=document.getElementById('questionPicker');if(!p)return;
  p.innerHTML='<option value="" disabled selected>Select question…</option>';
  extractedQuestions.forEach(q=>{const o=document.createElement('option');o.value=q.question_id;o.textContent=`${escapeHtml(q.question_id)}: ${escapeHtml(q.question_text.slice(0,35))}…`;p.appendChild(o)});
}

window.deleteQuestion = (qid) => {
  if(!confirm(`Remove ${escapeHtml(qid)}?`)) return;
  extractedQuestions = extractedQuestions.filter(q => q.question_id !== qid);
  delete coordMap[qid];
  renderQList(); renderQPicker(); renderCoordsList();
  notify(`Removed ${escapeHtml(qid)}`, 'info');
};

function renderQList(){
  const l=document.getElementById('extractedQuestionsList');if(!l)return;
  if(!extractedQuestions.length){l.innerHTML='<span class="text-muted" style="font-size:.75rem">None extracted yet.</span>';return}
  l.innerHTML='';extractedQuestions.forEach(q=>{
    const d=document.createElement('div');d.style.cssText='padding:.6rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm);display:flex;justify-content:space-between;align-items:center';
    const escapeHtml = (unsafe) => (unsafe ?? '').toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    d.innerHTML=`<div style="flex:1"><strong style="color:var(--accent);font-size:.75rem">${escapeHtml(q.question_id)}</strong>
      <div class="text-secondary" style="font-size:.75rem;margin-top:.15rem">${escapeHtml(q.question_text)}</div></div>
      <button onclick="deleteQuestion('${escapeHtml(q.question_id)}')" class="btn btn-danger" style="padding:.2rem;background:transparent;border:none;margin-left:.5rem"><svg class="icon-sm"><use href="#ico-x"/></svg></button>`;
    l.appendChild(d);
  });
}

function renderCoordsList(){
  const l=document.getElementById('mappedCoordsList');if(!l)return;
  const coords=Object.values(coordMap);
  if(!coords.length){l.innerHTML='<span class="text-muted" style="font-size:.75rem">No coordinates mapped yet.</span>';return}
  l.innerHTML='';coords.forEach(c=>{
    const d=document.createElement('div');d.style.cssText='padding:.4rem .6rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm);display:flex;justify-content:space-between;align-items:center';
    d.innerHTML=`<span style="font-weight:600;font-size:.75rem;color:var(--text-primary)">${escapeHtml(c.question_id)}</span><span style="display:flex;gap:.4rem;align-items:center"><span class="badge badge-info" style="font-size:.6rem">${escapeHtml(c.max_score||10)} pts</span><span class="badge badge-success" style="font-size:.6rem">Mapped</span></span>`;
    l.appendChild(d);
  });
}

function updateCanvasZoom(delta){
    const c=gc(); if(!c) return;
    const currentW = c.offsetWidth;
    const newW = Math.max(400, Math.min(3000, currentW + (delta * 100)));
    c.style.width = newW + 'px';
}

[qCanvas, aCanvas].forEach(c => {
    if(!c) return;
    c.addEventListener('wheel', e => {
        if(e.ctrlKey) {
            e.preventDefault();
            updateCanvasZoom(e.deltaY < 0 ? 1 : -1);
        }
    });
});

async function previewCrop(source){
  if(!sessionId||!currentSelection){notify('Draw a crop box first.','warning');return null}
  const m=c2o(currentSelection);
  const payload={source,page_index:source==='question'?+(document.getElementById('questionPageIndex')?.value||0):+(document.getElementById('answerPageIndex')?.value||0),
    sheet_index:source==='answer'?+(document.getElementById('answerSheetIndex')?.value||0):0,...m,clean:true};
  try{
    const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/crop/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    const url=`data:image/png;base64,${escapeHtml(d.preview_base64)}`;
    if(source==='question'){document.getElementById('questionCropPreview').src=url;document.getElementById('questionCropPreview').style.display='block';document.getElementById('questionCropPlaceholder').style.display='none'}
    else{document.getElementById('answerCropPreview').src=url;document.getElementById('answerCropPreview').style.display='block';document.getElementById('answerCropPlaceholder').style.display='none'}
    return{mapped:d.crop_box,dataUrl:url};
  }catch(err){notify(err.message,'error');return null}
}

// Canvas mouse
function onDown(e){const c=gc(),r=c.getBoundingClientRect();startPoint={x:e.clientX-r.left,y:e.clientY-r.top};isDragging=true}
function onMove(e){
  if(!isDragging||!startPoint)return;
  const c=gc(), r=c.getBoundingClientRect();
  const x=e.clientX-r.left, y=e.clientY-r.top;
  const scaleX = c.width / r.width;
  const scaleY = c.height / r.height;
  const sx = startPoint.x * scaleX, sy = startPoint.y * scaleY;
  const cx = x * scaleX, cy = y * scaleY;
  currentSelection={x:Math.min(sx,cx), y:Math.min(sy,cy), w:Math.abs(cx-sx), h:Math.abs(cy-sy)};
  drawPreview();
}
function onUp(){if(!isDragging)return;isDragging=false;if(currentSelection&&currentSelection.w<8)currentSelection=null;drawPreview()}
if(qCanvas){qCanvas.addEventListener('mousedown',onDown);qCanvas.addEventListener('mousemove',onMove)}
if(aCanvas){aCanvas.addEventListener('mousedown',onDown);aCanvas.addEventListener('mousemove',onMove)}
window.addEventListener('mouseup',onUp);

// Load previews
document.getElementById('loadQuestionPreview')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('Create a session first.','warning');activeCanvasKind='question';
  const pi=+(document.getElementById('questionPageIndex')?.value||0);
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/preview?source=question&page_index=${escapeHtml(pi)}`);if(!r.ok) { const errData = await r.json(); throw new Error(typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)); }
    const b=await r.blob();qImg.onload=()=>{const cw=qCanvas.parentElement.clientWidth;qCanvas.width=cw;qCanvas.height=Math.round(qImg.naturalHeight*(cw/qImg.naturalWidth));currentSelection=null;drawPreview()};
    qImg.src=URL.createObjectURL(b)}catch(err){notify(err.message,'error')}});

document.getElementById('loadAnswerPreview')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('Create a session first.','warning');activeCanvasKind='answer';
  const si=+(document.getElementById('answerSheetIndex')?.value||0),pi=+(document.getElementById('answerPageIndex')?.value||0);
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/preview?source=answer&sheet_index=${escapeHtml(si)}&page_index=${escapeHtml(pi)}`);if(!r.ok) { const errData = await r.json(); throw new Error(typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)); }
    const b=await r.blob();aImg.onload=()=>{const cw=aCanvas.parentElement.clientWidth;aCanvas.width=cw;aCanvas.height=Math.round(aImg.naturalHeight*(cw/aImg.naturalWidth));currentSelection=null;drawPreview()};
    aImg.src=URL.createObjectURL(b)}catch(err){notify(err.message,'error')}});

document.getElementById('previewQuestionCrop')?.addEventListener('click',()=>previewCrop('question'));
document.getElementById('previewAnswerCrop')?.addEventListener('click',()=>previewCrop('answer'));

document.getElementById('extractQuestion')?.addEventListener('click',async()=>{
  if(!sessionId||!currentSelection)return notify('Draw a crop box first.','warning');
  const btn=document.getElementById('extractQuestion');btn.textContent='Extracting…';btn.disabled=true;
  try{const pv=await previewCrop('question');if(!pv)throw new Error('Preview failed');
    const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/questions/from-crop`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({page_index:+(document.getElementById('questionPageIndex')?.value||0),...pv.mapped})});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    extractedQuestions=d.questions||[];renderQPicker();renderQList();populateRubricQuestionPicker();notify(`Extracted ${escapeHtml(d.question.question_id)}`,'success');currentSelection=null;drawPreview();
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Extract Question Text';btn.disabled=false}});

document.getElementById('useSelection')?.addEventListener('click',async()=>{
  const pk=document.getElementById('questionPicker');
  if(!currentSelection||!pk?.value)return notify('Select a question and draw a crop.','warning');
  try{const pv=await previewCrop('answer');if(!pv)return;
    const ms=parseFloat(document.getElementById('questionMaxScore')?.value)||10;
    coordMap[pk.value]={question_id:pk.value,question_text:(extractedQuestions.find(q=>q.question_id===pk.value)||{}).question_text||'',
      page_index:+(document.getElementById('answerPageIndex')?.value||0),...pv.mapped,marking_scheme:null,max_score:ms};
    renderCoordsList();notify(`Mapped ${escapeHtml(pk.value)}`,'success');currentSelection=null;drawPreview();pk.value='';
  }catch(err){notify(err.message,'error')}});

document.getElementById('saveCoords')?.addEventListener('click',async()=>{
  if(!sessionId)return;const coords=Object.values(coordMap);if(!coords.length)return notify('No coordinates.','warning');
  const btn=document.getElementById('saveCoords');btn.textContent='Saving…';btn.disabled=true;
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/coordinates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({coordinates:coords})});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);notify('Coordinates saved!','success');markStep('nav-crop',true);
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Save Coordinate Templates';btn.disabled=false}});

// ─── Pipeline Animations ───
function createCompletionBurst(stepEl){
  const indicator=stepEl.querySelector('.step-indicator');
  if(!indicator)return;
  const rect=indicator.getBoundingClientRect();
  const cx=rect.left+rect.width/2,cy=rect.top+rect.height/2;
  for(let i=0;i<10;i++){
    const angle=(i/10)*Math.PI*2+(Math.random()-.5)*.3;
    const dist=25+Math.random()*20;
    const p=document.createElement('div');
    p.className='burst-particle';
    p.style.left=cx+'px';p.style.top=cy+'px';
    p.style.setProperty('--bx',Math.cos(angle)*dist+'px');
    p.style.setProperty('--by',Math.sin(angle)*dist+'px');
    p.style.animationDelay=Math.random()*.08+'s';
    document.body.appendChild(p);
    p.addEventListener('animationend',()=>p.remove());
  }
}

// ─── Pipeline ───
function startPipelineTimer(){
  pipelineStartTime=Date.now();
  const el=document.getElementById('pipelineTimer');
  if(el)el.style.display='';
  pipelineTimerInterval=setInterval(()=>{
    const elapsed=Math.floor((Date.now()-pipelineStartTime)/1000);
    const m=String(Math.floor(elapsed/60)).padStart(2,'0');
    const s=String(elapsed%60).padStart(2,'0');
    if(el)el.textContent=`${escapeHtml(m)}:${escapeHtml(s)}`;
  },1000);
}
function stopPipelineTimer(){
  if(pipelineTimerInterval){clearInterval(pipelineTimerInterval);pipelineTimerInterval=null}
}

document.getElementById('runGrading')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('No session.','warning');
  const btn=document.getElementById('runGrading');btn.disabled=true;btn.textContent='Starting…';
  const steps=document.querySelectorAll('.pipeline-step');const statusText=document.getElementById('pipelineStatusText');const stepsContainer=document.getElementById('pipelineSteps');
  statusText.classList.remove('hidden');statusText.textContent='Starting pipeline…';
  startPipelineTimer();
  document.title='Running Pipeline... | GradeOps Vision';
  stepsContainer?.classList.add('pipeline-running');
  try{
    const r=await fetch(`/api/exams/${sessionId}/run`,{method:'POST'});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    const jobId=d.job_id;
    btn.textContent='Running…';
    const stepMap={rubrics:1,grading:2,plagiarism:3};
    let prevStepIdx=-1;
    const pollInterval=setInterval(async()=>{
      try{
        const pr=await fetch(`/api/exams/${sessionId}/job/${jobId}`);
        const pj=await pr.json();
        if(pj.step){
          const si=stepMap[pj.step]||0;
          if(si>prevStepIdx&&prevStepIdx>=0)createCompletionBurst(steps[prevStepIdx]);
          prevStepIdx=si;
          steps.forEach((s,i)=>{s.classList.toggle('active',i===si);s.classList.toggle('done',i<si)});
        }
        if(pj.total>0)statusText.textContent=`Processing ${pj.progress}/${pj.total}…`;
        if(pj.status==='done'){
          clearInterval(pollInterval);stopPipelineTimer();
          stepsContainer?.classList.remove('pipeline-running');
          steps.forEach((s,i)=>{const wasDone=s.classList.contains('done');s.classList.remove('active');s.classList.add('done');if(!wasDone)setTimeout(()=>createCompletionBurst(s),i*120)});
          const elapsed=Math.floor((Date.now()-pipelineStartTime)/1000);
          const sm=pj.summary||{};
          statusText.textContent=`Done in ${elapsed}s! ${sm.graded_entries||0} graded, ${sm.review_required||0} need review.`;
          notify('Pipeline complete!','success');markStep('nav-pipeline',true);
          await fetchDashboard();
          setTimeout(()=>switchView('view-results'),1500);
          btn.disabled=false;btn.textContent='Run Grading Pipeline';
        } else if(pj.status==='failed'){
          clearInterval(pollInterval);stopPipelineTimer();
          stepsContainer?.classList.remove('pipeline-running');
          steps.forEach(s=>{s.classList.remove('active','done')});
          notify(pj.error||'Pipeline failed','error');statusText.textContent='Pipeline failed.';
          btn.disabled=false;btn.textContent='Run Grading Pipeline';
        }
      }catch(pe){clearInterval(pollInterval);stopPipelineTimer();stepsContainer?.classList.remove('pipeline-running');notify('Polling error','error');btn.disabled=false;btn.textContent='Run Grading Pipeline'}
    },2000);
  }catch(err){stopPipelineTimer();stepsContainer?.classList.remove('pipeline-running');steps.forEach(s=>{s.classList.remove('active','done')});notify(err.message,'error');statusText.textContent='Pipeline failed.';btn.disabled=false;btn.textContent='Run Grading Pipeline'}
});

// ─── Dashboard Data ───
async function fetchDashboard(){
  if(!sessionId)return notify('No session.','warning');
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/dashboard`);const d=await r.json();if(!r.ok)throw new Error(d.detail);
    dashData=d;allResults=d.results||[];reviewQueue=d.review_queue||[];rIdx=0;
    
    // Populate reviewStatuses from loaded data
    reviewStatuses={};
    reviewQueue.forEach((item, index) => {
      if (item.review_status && item.review_status !== 'pending') {
        reviewStatuses[index] = item.review_status;
      }
    });

    renderStats(d.analytics);renderScoreDistribution(allResults);
    renderErrorDist(d.analytics?.error_distribution);renderRubrics(d.analytics?.rubrics);
    renderQuestionAnalytics(allResults);
    renderResultsTable(allResults);renderReviewUI();renderPlagiarism(d.plagiarism_flags);
    markStep('nav-results',true);
  }catch(err){notify(err.message,'error')}}
document.getElementById('loadDashboard')?.addEventListener('click',fetchDashboard);

function renderStats(a){
  if(!a)return;
  animateCounter('statTotal', a.total_graded);
  animateCounter('statAvgScore', parseFloat(a.avg_score), 1);
  animateCounter('statAvgAccuracy', Math.round(a.avg_accuracy*100), 0, '%');
  animateCounter('statReview', a.review_count);
  animateCounter('statPlagiarism', a.plagiarism_count);
  const pb=document.getElementById('plagiarismBadge');
  if(pb)pb.textContent=`${escapeHtml(a.plagiarism_count)} flags`;
}

function renderScoreDistribution(results){
  const card=document.getElementById('scoreDistCard'),container=document.getElementById('scoreHistogram');
  if(!results?.length){if(card)card.style.display='none';return}
  if(card)card.style.display='';
  const scores=results.map(r=>r.proposed_score||0);
  const maxScore=Math.max(...scores,10);
  const bucketSize=Math.max(1,Math.ceil(maxScore/6));
  const buckets=[];
  for(let i=0;i<maxScore;i+=bucketSize){
    const lo=i,hi=Math.min(i+bucketSize,maxScore);
    const count=scores.filter(s=>s>=lo&&(hi===maxScore?s<=hi:s<hi)).length;
    buckets.push({label:`${lo}-${hi}`,count});
  }
  const maxCount=Math.max(...buckets.map(b=>b.count),1);
  container.innerHTML='';
  buckets.forEach(b=>{
    const pct=Math.round(b.count/maxCount*100);
    container.innerHTML+=`<div class="histogram-bar-group">
      <div class="histogram-bar" style="height:${Math.max(pct,4)}%"><span class="bar-tooltip">${b.count} student${escapeHtml(b.count!==1?'s':'')}</span></div>
      <span class="histogram-label">${b.label}</span></div>`;
  });
}

function renderQuestionAnalytics(results){
  const card=document.getElementById('questionAnalyticsCard'),grid=document.getElementById('questionAnalyticsGrid');
  if(!results?.length){if(card)card.style.display='none';return}
  const byQ={};
  results.forEach(r=>{
    const qid=r.question_id||'unknown';
    if(!byQ[qid])byQ[qid]={scores:[],errors:{},maxScore:r.rubric?.max_score||10};
    byQ[qid].scores.push(r.proposed_score||0);
    (r.error_axes||[]).forEach(e=>{const label=typeof e==='string'?e:String(e);byQ[qid].errors[label]=(byQ[qid].errors[label]||0)+1});
  });
  if(!Object.keys(byQ).length){if(card)card.style.display='none';return}
  card.style.display='';grid.innerHTML='';
  const errColors={computational:'var(--warning)',conceptual:'var(--danger)',notation:'var(--info)',presentation:'var(--success)'};
  Object.entries(byQ).forEach(([qid,data])=>{
    const avg=data.scores.length?data.scores.reduce((a,b)=>a+b,0)/data.scores.length:0;
    const min=Math.min(...data.scores);
    const max=Math.max(...data.scores);
    const pct=data.maxScore>0?Math.round(avg/data.maxScore*100):0;
    let errHtml='';
    const totalErrors=Object.values(data.errors).reduce((a,b)=>a+b,0)||1;
    Object.entries(data.errors).forEach(([k,v])=>{
      const ePct=Math.round(v/totalErrors*100);
      errHtml+=`<div class="q-analytics-bar">
        <span style="min-width:80px;color:var(--text-muted);text-transform:capitalize">${k}</span>
        <div class="q-analytics-bar-track"><div class="q-analytics-bar-fill" style="width:${ePct}%;background:${escapeHtml(errColors[k]||'var(--accent)')}"></div></div>
        <span style="color:var(--text-primary);font-weight:700">${v}</span></div>`;
    });
    if(!errHtml)errHtml='<span class="text-muted" style="font-size:.75rem">No errors recorded</span>';
    grid.innerHTML+=`<div class="q-analytics-card">
      <div class="q-analytics-header">
        <span class="badge badge-info">${qid.toUpperCase()}</span>
        <div class="q-analytics-score">${avg.toFixed(1)}<span style="font-size:.75rem;font-weight:500;color:var(--text-muted)"> / ${data.maxScore}</span></div>
      </div>
      <div class="progress-bar" style="margin-bottom:.75rem"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:.6875rem;color:var(--text-muted);margin-bottom:.75rem">
        <span>Min: ${min.toFixed(1)}</span><span>${data.scores.length} graded</span><span>Max: ${max.toFixed(1)}</span>
      </div>
      ${errHtml}</div>`;
  });
}

function renderErrorDist(dist){
  const card=document.getElementById('errorDistCard'),container=document.getElementById('errorDistBars');
  if(!dist||!Object.keys(dist).length){card.style.display='none';return}
  card.style.display='';container.innerHTML='';
  const max=Math.max(...Object.values(dist),1);
  const colors={computational:'var(--warning)',conceptual:'var(--danger)',notation:'var(--info)',presentation:'var(--success)'};
  Object.entries(dist).forEach(([k,v])=>{
    const pct=Math.round(v/max*100);
    container.innerHTML+=`<div style="display:flex;align-items:center;gap:.75rem">
      <span style="min-width:100px;font-size:.75rem;font-weight:600;color:var(--text-secondary);text-transform:capitalize">${k}</span>
      <div class="progress-bar" style="flex:1"><div class="progress-fill" style="width:${pct}%;background:${escapeHtml(colors[k]||'var(--accent)')}"></div></div>
      <span style="font-size:.75rem;font-weight:700;color:var(--text-primary);min-width:24px;text-align:right">${v}</span></div>`;
  });
}

function renderRubrics(rubrics){ console.log("renderRubrics called with: ", rubrics);
  const card=document.getElementById('rubricViewerCard'),sel=document.getElementById('rubricQSelect'),detail=document.getElementById('rubricDetail'),badge=document.getElementById('rubricCountBadge');
  if(!rubrics||!Object.keys(rubrics).length){if(card)card.style.display='none';return}
  
  // Explicitly show the card if rubrics exist
  if(card){
    card.style.display='block';
    card.classList.remove('hidden');
  }

  const qids=Object.keys(rubrics);
  if(badge)badge.textContent=`${escapeHtml(qids.length)} rubric${escapeHtml(qids.length!==1?'s':'')}`;
  if(!sel||!detail)return;
  sel.innerHTML='';
  qids.forEach(qid=>{const o=document.createElement('option');o.value=qid;o.textContent=qid.toUpperCase();sel.appendChild(o)});
  function show(qid){
    const rb=rubrics[qid];if(!rb){detail.innerHTML='<p class="text-muted">No rubric data.</p>';return}
    let html=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <span class="badge badge-info" style="font-family: monospace; font-size: 1rem;">${escapeHtml(rb.question_id||qid)}</span><span style="font-size:1rem;font-weight:700;color:var(--accent)">Max Score: ${escapeHtml(rb.max_score||10)} pts</span></div>`;
    
    if (rb.criteria && rb.criteria.length > 0) {
      rb.criteria.forEach(c=>{
        html+=`<div class="criteria-item" style="padding: 0.8rem; border-left: 3px solid var(--accent); margin-bottom: 0.5rem; background: var(--bg-surface); border-radius: 4px;">
          <span class="criteria-desc" style="display: block; font-size: 0.95rem; margin-bottom: 0.3rem;">${escapeHtml(c.description)}</span>
          <span class="criteria-pts" style="display: inline-block; font-size: 0.8rem; font-weight: bold; background: var(--accent-dim); color: var(--accent); padding: 0.2rem 0.5rem; border-radius: 4px;">${escapeHtml(c.points)} pts</span>
        </div>`;
      });
    } else {
      html+=`<div class="criteria-item" style="padding: 1rem; text-align: center; background: var(--bg-surface); border-radius: 8px; border: 1px dashed var(--border-color);">
        <span class="criteria-desc text-muted">Criteria structure not detailed in DB. Showing only total max score.</span>
      </div>`;
    }
    detail.innerHTML=html;
  }
  sel.onchange=()=>show(sel.value);show(sel.value);
}

function renderResultsTable(results){
  const tb=document.getElementById('resultsTableBody');
  if(!tb)return;
  if(!results?.length){tb.innerHTML='<tr><td colspan="6" class="text-muted text-center" style="padding:2rem">No results.</td></tr>';return}
  tb.innerHTML='';
  
  results.forEach((r,idx)=>{
    const acc=r.accuracy!=null?Math.round(r.accuracy*100)+'%':'—';
    const accClass=r.accuracy>=.8?'badge-success':r.accuracy>=.6?'badge-warning':'badge-danger';
    const errors=(r.error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'—';
    const needsReview=r.needs_review?'<span class="badge badge-danger">Yes</span>':'<span class="badge badge-success">No</span>';
    const flagged=r.accuracy<.7||r.needs_review;
    
    const row=document.createElement('tr');
    row.className=`expandable ${escapeHtml(flagged?'row-flagged':'')}`;
    row.dataset.idx=idx;
    row.innerHTML=`<td>${escapeHtml(r.student_id||'—')}</td><td>${escapeHtml(r.question_id||'—')}</td>
      <td style="font-weight:700">${escapeHtml(r.proposed_score??'—')}</td><td><span class="badge ${escapeHtml(accClass)}">${escapeHtml(acc)}</span></td>
      <td>${errors}</td><td>${needsReview}</td>`;
    
    const detailRow=document.createElement('tr');
    detailRow.className='detail-row';
    detailRow.dataset.detail=idx;
    detailRow.innerHTML=`<td colspan="6">
        <div class="detail-content">
          <div class="detail-section"><h5>AI Justification</h5><p>${escapeHtml((r.justification||'No justification provided.').replace(/\n/g,'<br>'))}</p></div>
          <div class="detail-section"><h5>OCR Transcription</h5><p>${escapeHtml((r.transcription||'No transcription.').replace(/\n/g,'<br>'))}</p></div>
        </div></td>`;
    
    row.addEventListener('click',()=>{
      row.classList.toggle('expanded');
      detailRow.classList.toggle('visible');
    });
    
    tb.appendChild(row);
    tb.appendChild(detailRow);
  });
}

// ─── Search & Filter ───
document.getElementById('resultsSearch')?.addEventListener('input',e=>{filterResults()});
document.getElementById('resultsFilter')?.addEventListener('change',e=>{filterResults()});
function filterResults(){
  const query=(document.getElementById('resultsSearch')?.value||'').toLowerCase();
  const filter=document.getElementById('resultsFilter')?.value||'all';
  let filtered=allResults;
  if(query){
    filtered=filtered.filter(r=>
      (r.student_id||'').toLowerCase().includes(query)||
      (r.question_id||'').toLowerCase().includes(query)||
      (r.justification||'').toLowerCase().includes(query)
    );
  }
  if(filter==='review')filtered=filtered.filter(r=>r.needs_review||r.accuracy<.7);
  if(filter==='good')filtered=filtered.filter(r=>!r.needs_review&&r.accuracy>=.7);
  renderResultsTable(filtered);
}

// ─── CSV Export ───
document.getElementById('exportCSV')?.addEventListener('click',()=>{
  if(!allResults?.length)return notify('No results to export.','warning');
  const headers=['Student ID','Question ID','Score','Accuracy','Errors','Needs Review','Justification','Transcription'];
  const rows=allResults.map(r=>[
    r.student_id||'',r.question_id||'',r.proposed_score??'',
    r.accuracy!=null?Math.round(r.accuracy*100)+'%':'',
    (r.error_axes||[]).join('; '),r.needs_review?'Yes':'No',
    `"${escapeHtml((r.justification||'').replace(/"/g,'""'))}"`,
    `"${escapeHtml((r.transcription||'').replace(/"/g,'""'))}"`
  ]);
  const csv=[headers.join(','),...rows.map(r=>r.join(','))].join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=`gradeops_results_${escapeHtml(sessionId||'export')}.csv`;a.click();
  URL.revokeObjectURL(url);
  notify('CSV exported!','success');
});


// ─── PDF Report Export ───
document.getElementById('exportReport')?.addEventListener('click', () => {
  if(!sessionId) return notify('No session to export.', 'warning');
  window.open(`/api/exams/${sessionId}/report`, '_blank');
});

// ─── Review ───
function renderReviewUI(){
  document.getElementById('reviewCountBadge').textContent=`${escapeHtml(reviewQueue.length)} items`;
  if(reviewQueue.length){document.getElementById('reviewWorkspace').classList.remove('hidden');document.getElementById('reviewEmptyState').classList.add('hidden');updateReviewProgress();renderReviewItem()}
  else{document.getElementById('reviewWorkspace').classList.add('hidden');document.getElementById('reviewEmptyState').classList.remove('hidden')}
}

function updateReviewProgress(){
  const reviewed=Object.keys(reviewStatuses).length;
  const total=reviewQueue.length;
  const pct=total>0?Math.round(reviewed/total*100):0;
  const el=document.getElementById('reviewProgressText');if(el)el.textContent=`${escapeHtml(reviewed)} / ${escapeHtml(total)} reviewed`;
  const fill=document.getElementById('reviewProgressFill');if(fill)fill.style.width=`${pct}%`;
}

function renderReviewItem(){
  if(!reviewQueue.length||rIdx<0||rIdx>=reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  document.getElementById('reviewCounter').textContent=`${escapeHtml(rIdx+1)} / ${escapeHtml(reviewQueue.length)}`;
  document.getElementById('reviewStudentId').textContent=`Student: ${escapeHtml(item.student_id)}`;
  document.getElementById('reviewQuestionId').textContent=`Q: ${escapeHtml(item.question_id)}`;
  if(item.snippet_path){
    const fn=item.snippet_path.replace(/\\/g,'/').split('/').pop();
    document.getElementById('reviewCropImg').src=`/api/storage/${escapeHtml(fn)}`;
    document.getElementById('reviewCropImg').style.display='block';
  } else {
    document.getElementById('reviewCropImg').style.display='none';
  }
  document.getElementById('reviewTranscription').textContent=item.transcription||'[Empty]';
  document.getElementById('reviewScore').textContent=item.proposed_score??'—';
  document.getElementById('reviewMaxPoints').textContent=item.rubric?.max_score??'—';
  const axes=document.getElementById('reviewErrorAxes');
  if(axes)axes.innerHTML=(item.error_axes||[]).map(a=>`<span class="error-tag ${escapeHtml(a)}">${escapeHtml(a)}</span>`).join('')||'<span class="text-muted" style="font-size:.75rem">No errors.</span>';
  document.getElementById('reviewJustification').innerHTML=item.justification?item.justification.replace(/\n/g,'<br>'):'<span class="text-muted">No justification.</span>';
  const ab=document.getElementById('reviewAccuracyBadge');
  if(ab){const acc=Math.round((item.accuracy||0)*100);ab.textContent=`${escapeHtml(acc)}% Match`;ab.className=`badge ${escapeHtml(acc<70?'badge-warning':'badge-success')}`}
  const statusEl=document.getElementById('reviewCurrentStatus');
  const status=reviewStatuses[rIdx];
  if(status==='approved'){statusEl.className='review-status-indicator approved';statusEl.textContent='Approved'}
  else if(status==='overridden'){statusEl.className='review-status-indicator overridden';statusEl.textContent='Overridden'}
  else{statusEl.className='review-status-indicator pending';statusEl.textContent='Pending'}
}

function reviewNext(){if(rIdx<reviewQueue.length-1){rIdx++;renderReviewItem()}else notify('End of queue.','info')}
function reviewPrev(){if(rIdx>0){rIdx--;renderReviewItem()}}
function approveCurrent(){
  if(!reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  const btn = document.getElementById('btnApprove');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  fetch(`/api/exams/${escapeHtml(sessionId)}/review/${escapeHtml(item.id)}`,{
    method:'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'approved' })
  })
    .then(r=>{if(!r.ok)throw new Error('Failed to persist approval');return r.json()})
    .then(()=>{
      reviewStatuses[rIdx]='approved';
      updateReviewProgress();
      notify(`Approved ${escapeHtml(rIdx+1)}/${escapeHtml(reviewQueue.length)}`,'success');
      renderReviewItem();
      if(rIdx<reviewQueue.length-1)setTimeout(()=>reviewNext(),300);
    }).catch(err=>notify(err.message,'error'))
    .finally(()=>{
      btn.disabled = false;
      btn.innerHTML = '<svg class="icon-sm"><use href="#ico-check"/></svg> Approve (A)';
    });
}
function overrideCurrent(){
  if(!reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  const ns=prompt(`New score (max ${escapeHtml(item.rubric?.max_score||'?')}):`,item.proposed_score);
  if(ns!==null&&!isNaN(ns)){
    const newScore=parseFloat(ns);
    const btn = document.getElementById('btnOverride');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    fetch(`/api/exams/${escapeHtml(sessionId)}/review/${escapeHtml(item.id)}`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status: 'overridden', new_score:newScore})
    }).then(r=>{if(!r.ok)throw new Error('Failed to persist override');return r.json()})
      .then(()=>{
        item.proposed_score=newScore;
        reviewStatuses[rIdx]='overridden';
        updateReviewProgress();
        notify(`Overridden ${escapeHtml(rIdx+1)}/${escapeHtml(reviewQueue.length)}`,'success');
        renderReviewItem();

        const mainResult = allResults.find(r => r.id === item.id);
        if(mainResult) mainResult.proposed_score = newScore;
        filterResults();

        if(rIdx<reviewQueue.length-1)setTimeout(()=>reviewNext(),300);
      }).catch(err=>notify(err.message,'error'))
      .finally(()=>{
        btn.disabled = false;
        btn.innerHTML = '<svg class="icon-sm"><use href="#ico-edit"/></svg> Override (O)';
      });
  }
}
document.getElementById('btnNext')?.addEventListener('click',reviewNext);
document.getElementById('btnPrev')?.addEventListener('click',reviewPrev);
document.getElementById('btnApprove')?.addEventListener('click',approveCurrent);
document.getElementById('btnOverride')?.addEventListener('click',overrideCurrent);

function regradeCurrent(){
  if(!reviewQueue.length||!sessionId)return;
  const item=reviewQueue[rIdx];
  const btn=document.getElementById('btnRegrade');
  if(!confirm(`Re-grade ${item.student_id} / ${item.question_id}? This will re-run OCR and AI grading.`))return;
  btn.disabled=true;btn.textContent='Re-grading…';
  fetch(`/api/exams/${sessionId}/regrade/${item.id}`,{method:'POST'})
    .then(r=>{if(!r.ok)throw new Error('Re-grade failed');return r.json()})
    .then(d=>{
      const updated=d.result;
      if(updated){
        item.proposed_score=updated.proposed_score;
        item.justification=updated.justification;
        item.transcription=updated.transcription;
        item.error_axes=updated.error_axes||[];
        item.accuracy=updated.accuracy;
        item.needs_review=updated.needs_review;
        delete reviewStatuses[rIdx];
      }
      updateReviewProgress();renderReviewItem();
      notify('Re-grade complete','success');
      const mainResult=allResults.find(r=>r.id===item.id);
      if(mainResult&&updated){Object.assign(mainResult,updated)}
      filterResults();
    }).catch(err=>notify(err.message,'error'))
    .finally(()=>{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-refresh"/></svg> Re-grade (R)'});
}
document.getElementById('btnRegrade')?.addEventListener('click',regradeCurrent);

// ─── Plagiarism ───
function renderPlagiarism(flags){
  const container=document.getElementById('plagiarismList');
  if(!container)return;
  if(!flags?.length){
    container.innerHTML='<div class="card" style="text-align:center;padding:3rem"><p class="text-muted">No plagiarism data detected.</p></div>';
    return;
  }
  container.innerHTML='';
  flags.forEach(f=>{
    const p1=f.pair[0],p2=f.pair[1];
    const conf=Math.round(f.confidence*100);
    const errs=(f.shared_error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'None';
    container.innerHTML+=`<div class="plagiarism-item">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
        <div style="display:flex;align-items:center;gap:.75rem"><span class="badge badge-info">${escapeHtml(p1)}</span><span style="color:var(--text-muted)">↔</span><span class="badge badge-info">${escapeHtml(p2)}</span></div>
        <div class="accuracy-circle" style="width:40px;height:40px;font-size:.75rem;background:rgba(239,68,68,.1);border-color:var(--danger);color:var(--danger)">${escapeHtml(conf)}%</div>
      </div>
      <div style="margin-bottom:.5rem;font-size:.8125rem"><strong style="color:var(--text-secondary)">Reason:</strong> ${escapeHtml(f.reason)}</div>
      <div style="font-size:.8125rem"><strong style="color:var(--text-secondary)">Shared Errors:</strong> ${errs}</div></div>`;
  });
}

// ─── Sandbox ───
let selectedPreset='math';
function updateSandboxUI(){
  document.querySelectorAll('.sandbox-preset').forEach(p=>{
    const isSelected = p.id === `preset-${escapeHtml(selectedPreset)}`;
    p.classList.toggle('active', isSelected);
  });
  const customCard = document.getElementById('preset-custom');
  if(customCard){
    customCard.style.opacity = selectedPreset==='custom' ? '1' : '0.65';
  }
}

document.querySelectorAll('.sandbox-preset').forEach(p=>{
  p.addEventListener('click',()=>{
    selectedPreset=p.id.replace('preset-','');
    updateSandboxUI();
  });
});
updateSandboxUI();

document.getElementById('runSandbox')?.addEventListener('click', async () => {
  const btn = document.getElementById('runSandbox');
  btn.disabled = true;
  btn.textContent = 'Generating...';

  const status = document.getElementById('sandboxStatusText');
  document.getElementById('sandboxStatus').classList.remove('hidden');
  status.textContent = 'GENERATING DATA';

  try {
    const body = { preset: selectedPreset };
    if (selectedPreset === 'custom') {
      body.students = parseInt(document.getElementById('sandboxStudents')?.value) || 10;
      body.questions = parseInt(document.getElementById('sandboxQuestions')?.value) || 4;
      body.max_score = parseInt(document.getElementById('sandboxMaxScore')?.value) || 10;
      body.include_plagiarism = document.getElementById('sandboxPlagiarism')?.checked ?? true;
      body.include_low_conf = document.getElementById('sandboxLowConf')?.checked ?? true;
    }
    const r = await fetch('/api/sandbox/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail);

    sessionId = d.session_id;
    status.textContent = `Loaded ${escapeHtml(selectedPreset)} Preset: ${escapeHtml(sessionId)}`;
    status.style.color = '#10b981';
    notify(`${escapeHtml(selectedPreset)} sandbox generated!`, 'success');

    await fetchDashboard();
    setTimeout(() => switchView('view-results'), 1200);
  } catch(err) {
    status.textContent = 'FAILED';
    status.style.color = '#ef4444';
    notify(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate & Load';
  }
});

// ─── Rubric Editor ───
function populateRubricQuestionPicker(){
  const sel=document.getElementById('rubricQuestionPicker');if(!sel)return;
  sel.innerHTML='<option value="" disabled selected>Select question...</option>';
  extractedQuestions.forEach(q=>{
    const o=document.createElement('option');o.value=q.question_id;
    o.textContent=`${q.question_id}: ${q.question_text.slice(0,40)}…`;sel.appendChild(o);
  });
}

function addCriterionRow(desc='',pts='',type='conceptual'){
  const container=document.getElementById('criteriaRows');if(!container)return;
  const row=document.createElement('div');
  row.style.cssText='display:flex;gap:.5rem;align-items:center';
  row.innerHTML=`<input type="text" placeholder="Criterion description" value="${escapeHtml(desc)}" class="form-control criterion-desc" style="flex:2;font-size:.8rem">
    <input type="number" min="0" step="0.5" placeholder="Pts" value="${escapeHtml(pts)}" class="form-control criterion-pts" style="width:70px;font-size:.8rem">
    <select class="form-control criterion-type" style="width:130px;font-size:.8rem">
      <option value="conceptual"${type==='conceptual'?' selected':''}>Conceptual</option>
      <option value="computational"${type==='computational'?' selected':''}>Computational</option>
      <option value="notation"${type==='notation'?' selected':''}>Notation</option>
      <option value="presentation"${type==='presentation'?' selected':''}>Presentation</option>
    </select>
    <button class="btn btn-danger" style="padding:.2rem .4rem;background:transparent;border:none" onclick="this.parentElement.remove()"><svg class="icon-sm"><use href="#ico-x"/></svg></button>`;
  container.appendChild(row);
}

document.getElementById('addCriterionBtn')?.addEventListener('click',()=>addCriterionRow());

function collectRubricForm(){
  const qid=document.getElementById('rubricQuestionPicker')?.value;
  const maxScore=parseFloat(document.getElementById('rubricMaxScore')?.value)||10;
  if(!qid){notify('Select a question first.','warning');return null}
  const rows=document.querySelectorAll('#criteriaRows > div');
  const criteria=[];
  rows.forEach(row=>{
    const desc=row.querySelector('.criterion-desc')?.value?.trim();
    const pts=parseFloat(row.querySelector('.criterion-pts')?.value)||0;
    const type=row.querySelector('.criterion-type')?.value||'conceptual';
    if(desc)criteria.push({description:desc,points:pts,type});
  });
  if(!criteria.length){notify('Add at least one criterion.','warning');return null}
  return {question_id:qid,max_score:maxScore,criteria};
}

document.getElementById('saveRubricBtn')?.addEventListener('click',async()=>{
  const payload=collectRubricForm();if(!payload)return;
  if(!sessionId){notify('No active session.','warning');return}
  const btn=document.getElementById('saveRubricBtn');btn.disabled=true;btn.textContent='Saving…';
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to save rubric');
    notify(`Rubric saved for ${payload.question_id}`,'success');
    await loadSavedRubrics();
  }catch(err){notify(err.message,'error')}
  finally{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-save"/></svg> Save Rubric'}
});

document.getElementById('aiGenerateRubricBtn')?.addEventListener('click',async()=>{
  const qid=document.getElementById('rubricQuestionPicker')?.value;
  if(!qid){notify('Select a question first.','warning');return}
  if(!sessionId){notify('No active session.','warning');return}
  const btn=document.getElementById('aiGenerateRubricBtn');btn.disabled=true;btn.textContent='Generating…';
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics/${qid}/generate`,{method:'POST'});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to generate rubric');
    const rubric=d.rubric;
    document.getElementById('rubricMaxScore').value=rubric.max_score||10;
    document.getElementById('criteriaRows').innerHTML='';
    (rubric.criteria||[]).forEach(c=>addCriterionRow(c.description,c.points,c.type||'conceptual'));
    notify('AI rubric generated — review and save.','success');
  }catch(err){notify(err.message,'error')}
  finally{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-zap"/></svg> AI Generate'}
});

async function loadSavedRubrics(){
  if(!sessionId)return;
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics`);
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to load rubrics');
    renderSavedRubrics(d.rubrics||[]);
  }catch(err){notify(err.message,'error')}
}

function renderSavedRubrics(rubrics){
  const list=document.getElementById('savedRubricsList');
  const badge=document.getElementById('rubricEditorCount');
  const entries=Array.isArray(rubrics)?rubrics:Object.entries(rubrics||{}).map(([qid,rb])=>({question_id:qid,rubric_json:rb}));
  if(badge)badge.textContent=`${entries.length} rubric${entries.length!==1?'s':''} saved`;
  if(!list)return;
  if(!entries.length){list.innerHTML='<span class="text-muted" style="font-size:.75rem">No rubrics saved yet.</span>';return}
  list.innerHTML='';
  entries.forEach(r=>{
    const rb=r.rubric_json||{};
    const criteriaCount=(rb.criteria||[]).length;
    const card=document.createElement('div');
    card.style.cssText='padding:.75rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm)';
    card.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem">
      <span class="badge badge-info">${escapeHtml(r.question_id)}</span>
      <span style="font-size:.75rem;color:var(--text-muted)">${escapeHtml(rb.max_score||'?')} pts · ${escapeHtml(criteriaCount)} criteria</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:.25rem;margin-bottom:.5rem">
      ${(rb.criteria||[]).map(c=>`<div style="font-size:.75rem;color:var(--text-secondary);padding-left:.5rem;border-left:2px solid var(--accent)">
        ${escapeHtml(c.description)} <span style="font-weight:700">(${escapeHtml(c.points)} pts)</span></div>`).join('')}
    </div>
    <div style="display:flex;gap:.4rem">
      <button class="btn btn-secondary rubric-edit-btn" data-qid="${escapeHtml(r.question_id)}" style="padding:.2rem .5rem;font-size:.7rem">Edit</button>
      <button class="btn btn-danger rubric-delete-btn" data-qid="${escapeHtml(r.question_id)}" style="padding:.2rem .5rem;font-size:.7rem;background:transparent;border:1px solid var(--danger);color:var(--danger)">Delete</button>
    </div>`;
    card.querySelector('.rubric-edit-btn').addEventListener('click',()=>{
      document.getElementById('rubricQuestionPicker').value=r.question_id;
      document.getElementById('rubricMaxScore').value=rb.max_score||10;
      document.getElementById('criteriaRows').innerHTML='';
      (rb.criteria||[]).forEach(c=>addCriterionRow(c.description,c.points,c.type||'conceptual'));
    });
    card.querySelector('.rubric-delete-btn').addEventListener('click',async()=>{
      if(!confirm(`Delete rubric for ${r.question_id}?`))return;
      try{
        const res=await fetch(`/api/exams/${sessionId}/rubrics/${r.question_id}`,{method:'DELETE'});
        if(!res.ok)throw new Error('Delete failed');
        notify(`Rubric for ${r.question_id} deleted`,'info');
        await loadSavedRubrics();
      }catch(err){notify(err.message,'error')}
    });
    list.appendChild(card);
  });
}

document.getElementById('refreshRubricsBtn')?.addEventListener('click',loadSavedRubrics);

// ─── Keyboard Shortcuts ───
window.addEventListener('keydown',e=>{
  const active=document.querySelector('.view-section:not(.hidden)');
  if(active?.id==='view-review'&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'){
    if(e.key==='ArrowRight')reviewNext();if(e.key==='ArrowLeft')reviewPrev();
    if(e.key.toLowerCase()==='a')approveCurrent();if(e.key.toLowerCase()==='o'){e.preventDefault();overrideCurrent()}
    if(e.key.toLowerCase()==='r'){e.preventDefault();regradeCurrent()}}
});

// ─── Drag & Drop ───
['dz-qp','dz-as'].forEach(id=>{
  const dz=document.getElementById(id);if(!dz)return;
  dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('dragover')});
  dz.addEventListener('dragleave',()=>dz.classList.remove('dragover'));
  dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('dragover');
    const input=dz.querySelector('input[type=file]');if(input&&e.dataTransfer.files.length){input.files=e.dataTransfer.files;
      const labelId=input.id==='file-qp'?'label-qp':'label-as';updateFileName(input,labelId,input.multiple)}});
});

// ─── Student Reports ───
function renderStudentReports(filter=''){
  const container=document.getElementById('studentReportsList');
  const badge=document.getElementById('studentCountBadge');
  if(!container)return;
  if(!allResults?.length){
    container.innerHTML='<div class="card" style="text-align:center;padding:3rem"><p class="text-muted">No grading results available. Run the pipeline first.</p></div>';
    if(badge)badge.textContent='0 students';
    return;
  }
  const byStudent={};
  allResults.forEach(r=>{
    const sid=r.student_id||'Unknown';
    if(!byStudent[sid])byStudent[sid]={results:[],totalScore:0,totalMax:0,errors:{}};
    const s=byStudent[sid];
    s.results.push(r);
    s.totalScore+=r.proposed_score||0;
    s.totalMax+=(r.rubric?.max_score||10);
    (r.error_axes||[]).forEach(e=>{s.errors[e]=(s.errors[e]||0)+1});
  });

  let students=Object.entries(byStudent);
  if(filter){
    const q=filter.toLowerCase();
    students=students.filter(([sid])=>sid.toLowerCase().includes(q));
  }
  if(badge)badge.textContent=`${students.length} student${students.length!==1?'s':''}`;

  if(!students.length){container.innerHTML='<div class="card" style="text-align:center;padding:2rem"><p class="text-muted">No students match your search.</p></div>';return}

  container.innerHTML='';
  students.sort((a,b)=>a[0].localeCompare(b[0]));
  students.forEach(([sid,data])=>{
    const pct=data.totalMax>0?Math.round(data.totalScore/data.totalMax*100):0;
    const grade=pct>=90?'A+':pct>=80?'A':pct>=70?'B':pct>=60?'C':pct>=50?'D':'F';
    const gradeColor=pct>=70?'var(--success)':pct>=50?'var(--warning)':'var(--danger)';

    const errorEntries=Object.entries(data.errors).sort((a,b)=>b[1]-a[1]);
    const focusAreas=errorEntries.slice(0,3).map(([e,c])=>{
      const tips={
        conceptual:'Review core concepts and definitions',
        computational:'Practice numerical calculations and formulas',
        notation:'Pay attention to proper notation and symbols',
        presentation:'Improve answer structure and clarity',
        reasoning:'Strengthen logical reasoning and proof steps',
        formatting:'Follow required answer format guidelines'
      };
      return `<strong style="text-transform:capitalize">${escapeHtml(e)}</strong> (${c} issue${c>1?'s':''}): ${tips[e]||'Review this area'}`;
    });

    let qRows='';
    data.results.forEach(r=>{
      const max=r.rubric?.max_score||10;
      const qPct=max>0?Math.round((r.proposed_score||0)/max*100):0;
      const barColor=qPct>=70?'var(--success)':qPct>=50?'var(--warning)':'var(--danger)';
      const errs=(r.error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'<span class="text-muted" style="font-size:.7rem">None</span>';
      qRows+=`<tr>
        <td style="font-weight:600">${escapeHtml(r.question_id||'—')}</td>
        <td><span style="font-weight:700">${r.proposed_score??'—'}</span><span class="text-muted"> / ${max}</span></td>
        <td><div class="progress-bar" style="width:80px;display:inline-flex"><div class="progress-fill" style="width:${qPct}%;background:${barColor}"></div></div> <span style="font-size:.7rem;font-weight:600">${qPct}%</span></td>
        <td>${errs}</td>
        <td style="font-size:.75rem;color:var(--text-secondary);max-width:300px;white-space:normal;line-height:1.4">${escapeHtml((r.justification||'—').slice(0,150))}${(r.justification||'').length>150?'…':''}</td>
      </tr>`;
    });

    const card=document.createElement('div');
    card.className='card';
    card.style.cssText='margin-bottom:1rem;padding:0;overflow:hidden';
    card.innerHTML=`
      <div style="display:flex;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid var(--border-color);cursor:pointer" class="student-report-header">
        <div style="display:flex;align-items:center;gap:1rem">
          <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent-secondary));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.8rem;color:#fff">${escapeHtml(sid.charAt(0).toUpperCase())}</div>
          <div>
            <div style="font-weight:700;font-size:.9375rem;color:var(--text-primary)">${escapeHtml(sid)}</div>
            <div style="font-size:.75rem;color:var(--text-muted)">${data.results.length} question${data.results.length!==1?'s':''} graded</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:1.25rem">
          <div style="text-align:right">
            <div style="font-size:.75rem;color:var(--text-muted)">Total Score</div>
            <div style="font-weight:800;font-size:1.1rem;color:var(--text-primary)">${data.totalScore.toFixed(1)} <span style="font-size:.75rem;font-weight:500;color:var(--text-muted)">/ ${data.totalMax}</span></div>
          </div>
          <div style="width:48px;height:48px;border-radius:50%;border:3px solid ${gradeColor};display:flex;align-items:center;justify-content:center;flex-direction:column">
            <span style="font-weight:800;font-size:.875rem;color:${gradeColor}">${grade}</span>
            <span style="font-size:.55rem;color:var(--text-muted)">${pct}%</span>
          </div>
        </div>
      </div>
      <div class="student-report-body" style="display:none;padding:1rem 1.25rem">
        <table class="data-table" style="margin-bottom:1rem">
          <thead><tr><th>Question</th><th>Score</th><th>Progress</th><th>Errors</th><th>Feedback</th></tr></thead>
          <tbody>${qRows}</tbody>
        </table>
        ${errorEntries.length?`<div style="background:rgba(6,10,20,.4);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:1rem;margin-top:.75rem">
          <h4 style="font-size:.8125rem;margin-bottom:.6rem;color:var(--text-primary)">Areas to Focus On</h4>
          <ul style="margin:0;padding-left:1.25rem;list-style:disc">${focusAreas.map(f=>`<li style="font-size:.8125rem;color:var(--text-secondary);margin-bottom:.35rem;line-height:1.5">${f}</li>`).join('')}</ul>
        </div>`:'<p class="text-muted" style="font-size:.8125rem">No specific issues found — great work!</p>'}
        ${errorEntries.length?`<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem">${errorEntries.map(([e,c])=>`<span class="error-tag ${escapeHtml(e)}" style="font-size:.7rem">${escapeHtml(e)} x${c}</span>`).join('')}</div>`:''}
      </div>`;
    card.querySelector('.student-report-header').addEventListener('click',()=>{
      const body=card.querySelector('.student-report-body');
      body.style.display=body.style.display==='none'?'block':'none';
    });
    container.appendChild(card);
  });
}

document.getElementById('studentSearch')?.addEventListener('input',e=>{
  renderStudentReports(e.target.value);
});

// ─── Visual Enhancements ───

// 4. Animated Stat Counters
function animateCounter(elementId, target, decimals=0, suffix='') {
  const el=document.getElementById(elementId);
  if(!el) return;
  const targetNum=parseFloat(target)||0;
  if(targetNum===0){el.textContent='0'+suffix;return}
  const duration=1200;
  const startTime=performance.now();
  function tick(now){
    const elapsed=now-startTime;
    const progress=Math.min(elapsed/duration,1);
    const eased=1-Math.pow(1-progress,3);
    const current=targetNum*eased;
    el.textContent=current.toFixed(decimals)+suffix;
    if(progress<1)requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// 3. Staggered Entrance Animations
function staggerChildren(parent){
  if(!parent) return;
  const children=parent.querySelectorAll('.card, .stat-card, .stat-grid, .pipeline-steps, h2, .tab-bar, .table-toolbar, .review-nav, .review-progress, .analytics-grid');
  children.forEach((child,i)=>{
    child.classList.remove('cascade-child');
    child.style.animationDelay='';
    void child.offsetWidth;
    child.classList.add('cascade-child');
    child.style.animationDelay=`${i*70}ms`;
    child.addEventListener('animationend',()=>{
      child.classList.remove('cascade-child');
      child.style.animationDelay='';
    },{once:true});
  });
}

// 6. Floating Particle Dots (optimized)
function initParticles(){
  const canvas=document.getElementById('particleCanvas');
  if(!canvas||matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx=canvas.getContext('2d');
  const COUNT=22;
  let mouse={x:-1000,y:-1000};
  let running=true;

  function resize(){canvas.width=window.innerWidth;canvas.height=window.innerHeight}
  resize();
  window.addEventListener('resize',resize);
  document.addEventListener('mousemove',e=>{mouse.x=e.clientX;mouse.y=e.clientY},{passive:true});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){running=false}
    else{running=true;requestAnimationFrame(draw)}
  });

  const particles=[];
  for(let i=0;i<COUNT;i++){
    const r=Math.random()*2.2+0.6;
    const hue=160+Math.random()*30;
    const alpha=Math.random()*0.5+0.15;
    const size=Math.ceil((r+2)*4);
    const sprite=document.createElement('canvas');
    sprite.width=sprite.height=size;
    const sc=sprite.getContext('2d');
    const c=size/2;
    const g=sc.createRadialGradient(c,c,0,c,c,r*2);
    g.addColorStop(0,`hsla(${hue},70%,60%,${alpha})`);
    g.addColorStop(1,`hsla(${hue},70%,60%,0)`);
    sc.fillStyle=g;
    sc.fillRect(0,0,size,size);
    particles.push({
      x:Math.random()*canvas.width,y:Math.random()*canvas.height,
      vx:(Math.random()-0.5)*0.35,vy:(Math.random()-0.5)*0.35,
      r,alpha,hue,sprite,sz:size
    });
  }

  function draw(){
    if(!running)return;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    for(let i=0;i<particles.length;i++){
      const p=particles[i];
      p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x=canvas.width;if(p.x>canvas.width)p.x=0;
      if(p.y<0)p.y=canvas.height;if(p.y>canvas.height)p.y=0;
      const dx=mouse.x-p.x,dy=mouse.y-p.y;
      const md=Math.sqrt(dx*dx+dy*dy);
      const mi=md<200?1-md/200:0;
      if(mi>0.01){
        const dr=p.r+mi*2,da=p.alpha+mi*0.3;
        ctx.beginPath();ctx.arc(p.x,p.y,dr,0,Math.PI*2);
        const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,dr*2);
        g.addColorStop(0,`hsla(${p.hue},70%,60%,${da})`);
        g.addColorStop(1,`hsla(${p.hue},70%,60%,0)`);
        ctx.fillStyle=g;ctx.fill();
      } else {
        ctx.drawImage(p.sprite,p.x-p.sz/2,p.y-p.sz/2);
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}

// 8. Button Ripple Effect
document.addEventListener('click',e=>{
  const btn=e.target.closest('.btn');
  if(!btn) return;
  const rect=btn.getBoundingClientRect();
  const ripple=document.createElement('span');
  ripple.className='btn-ripple';
  const size=Math.max(rect.width,rect.height);
  ripple.style.width=ripple.style.height=size+'px';
  ripple.style.left=(e.clientX-rect.left-size/2)+'px';
  ripple.style.top=(e.clientY-rect.top-size/2)+'px';
  btn.appendChild(ripple);
  ripple.addEventListener('animationend',()=>ripple.remove());
});

// 9. Tab Title Updates
function updateTabTitle(viewId){
  const titles={
    'view-upload':'Upload','view-sandbox':'Sandbox','view-crop':'Cropping Studio',
    'view-pipeline':'Pipeline','view-rubrics':'Rubrics','view-results':'Results & Analytics',
    'view-review':'Review Queue','view-plagiarism':'Plagiarism','view-students':'Student Reports'
  };
  const section=titles[viewId]||'Dashboard';
  const status=sessionId?` [${sessionId.slice(0,8)}]`:'';
  document.title=`${section}${status} | GradeOps Vision`;
}

// Init visual enhancements
initParticles();
staggerChildren(document.querySelector('.view-section:not(.hidden)'));
=======
const escapeHtml = (unsafe) => (unsafe ?? '').toString().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
// ─── State ───
let sessionId=null,extractedQuestions=[],coordMap={},currentSelection=null,activeCanvasKind="question",isDragging=false,startPoint=null;
const qImg=new Image(),aImg=new Image();
let dashData=null,reviewQueue=[],allResults=[],rIdx=0;
let reviewStatuses={};
let pipelineTimerInterval=null,pipelineStartTime=null;

// ─── DOM refs ───
const navItems=document.querySelectorAll('.nav-item'),views=document.querySelectorAll('.view-section');
const qCanvas=document.getElementById("questionCanvas"),qCtx=qCanvas?.getContext("2d");
const aCanvas=document.getElementById("answerCanvas"),aCtx=aCanvas?.getContext("2d");

// ─── Helpers ───
function notify(msg,type='info'){
  if (typeof msg === 'object') { msg = JSON.stringify(msg); }
  const c=document.getElementById('notificationContainer');if(!c)return;
  const e=document.createElement('div');
  e.className=`notification ${escapeHtml(type)}`;
  const iconIds={success:'ico-check',error:'ico-x',warning:'ico-alert',info:'ico-info'};
  e.innerHTML=`<svg class="icon icon-sm"><use href="#${iconIds[type]||'ico-info'}"/></svg><span>${escapeHtml(msg)}</span>`;
  c.appendChild(e);
  setTimeout(()=>{e.style.opacity='0';e.style.transform='translateY(-10px)';e.style.transition='all .3s';setTimeout(()=>e.remove(),300)},3500);
}
function updateFileName(input,labelId,multi=false){
  const l=document.getElementById(labelId);if(!l)return;
  if(input.files?.length){l.classList.remove('hidden');l.textContent=multi?`${escapeHtml(input.files.length)} files`:input.files[0].name}
  else l.classList.add('hidden');
}

// ─── Navigation ───
function switchView(id){
  navItems.forEach(n=>{n.classList.toggle('active',n.dataset.target===id)});
  views.forEach(v=>{
    const show=v.id===id;
    v.classList.toggle('hidden',!show);
    if(show){v.classList.remove('view-entering');void v.offsetWidth;v.classList.add('view-entering');staggerChildren(v)}
  });
  if(id==='view-rubrics'){populateRubricQuestionPicker();loadSavedRubrics()}
  if(id==='view-students'){renderStudentReports()}
  updateTabTitle(id);
}
navItems.forEach(n=>n.addEventListener('click',()=>switchView(n.dataset.target)));
function markStep(id,done){document.getElementById(id)?.classList.toggle('completed',done)}

// ─── Upload ───
document.getElementById('uploadForm')?.addEventListener('submit',async e=>{
  e.preventDefault();const btn=document.getElementById('btn-upload');btn.textContent='Uploading…';btn.disabled=true;
  try{
    const r=await fetch("/api/exams/upload",{method:"POST",body:new FormData(e.target)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    sessionId=d.session_id;extractedQuestions=d.questions||[];coordMap={};
    notify('Upload successful!','success');markStep('nav-upload',true);
    document.getElementById('uploadResultContainer').classList.remove('hidden');
    document.getElementById('uploadResult').textContent=`Session: ${escapeHtml(sessionId)}`;
    renderQPicker();renderQList();populateRubricQuestionPicker();
    setTimeout(()=>switchView('view-crop'),1200);
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Upload & Create Session';btn.disabled=false}
});

// ─── Cropping ───
function setCropTab(kind){
  if(kind==='answer'&&!extractedQuestions.length){notify('Extract at least one question first.','warning');return}
  activeCanvasKind=kind;
  document.getElementById('questionTabPanel').classList.toggle('hidden',kind!=='question');
  document.getElementById('answerTabPanel').classList.toggle('hidden',kind!=='answer');
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',i===(kind==='question'?0:1)));
  currentSelection=null;drawPreview();
}
document.getElementById('tabQuestions')?.addEventListener('click',()=>setCropTab('question'));
document.getElementById('tabAnswers')?.addEventListener('click',()=>setCropTab('answer'));

function gc(){return activeCanvasKind==='question'?qCanvas:aCanvas}
function gx(){return activeCanvasKind==='question'?qCtx:aCtx}
function gi(){return activeCanvasKind==='question'?qImg:aImg}

function drawPreview(){
  const c=gc(),x=gx(),img=gi();if(!img.src||!c||!x)return;
  x.clearRect(0,0,c.width,c.height);x.drawImage(img,0,0,c.width,c.height);
  if(currentSelection){
    x.fillStyle='rgba(0,0,0,0.45)';
    x.beginPath();
    x.rect(0, 0, c.width, c.height);
    x.rect(currentSelection.x, currentSelection.y, currentSelection.w, currentSelection.h);
    x.fill('evenodd');
    
    x.strokeStyle='#818cf8';x.lineWidth=2;
    x.strokeRect(currentSelection.x,currentSelection.y,currentSelection.w,currentSelection.h);
    
    x.fillStyle='#fff';const s=6,{x:sx,y:sy,w:sw,h:sh}=currentSelection;
    [[sx,sy],[sx+sw/2,sy],[sx+sw,sy],[sx,sy+sh/2],[sx+sw,sy+sh/2],[sx,sy+sh],[sx+sw/2,sy+sh],[sx+sw,sy+sh]]
      .forEach(p=>x.fillRect(p[0]-s/2,p[1]-s/2,s,s));
  }
}

function c2o(sel){const c=gc(),img=gi(),sx=img.naturalWidth/c.width,sy=img.naturalHeight/c.height;
  return{x:Math.max(0,Math.round(sel.x*sx)),y:Math.max(0,Math.round(sel.y*sy)),w:Math.max(1,Math.round(sel.w*sx)),h:Math.max(1,Math.round(sel.h*sy))}}

function renderQPicker(){
  const p=document.getElementById('questionPicker');if(!p)return;
  p.innerHTML='<option value="" disabled selected>Select question…</option>';
  extractedQuestions.forEach(q=>{const o=document.createElement('option');o.value=q.question_id;o.textContent=`${escapeHtml(q.question_id)}: ${escapeHtml(q.question_text.slice(0,35))}…`;p.appendChild(o)});
}

window.deleteQuestion = (qid) => {
  if(!confirm(`Remove ${escapeHtml(qid)}?`)) return;
  extractedQuestions = extractedQuestions.filter(q => q.question_id !== qid);
  delete coordMap[qid];
  renderQList(); renderQPicker(); renderCoordsList();
  notify(`Removed ${escapeHtml(qid)}`, 'info');
};

function renderQList(){
  const l=document.getElementById('extractedQuestionsList');if(!l)return;
  if(!extractedQuestions.length){l.innerHTML='<span class="text-muted" style="font-size:.75rem">None extracted yet.</span>';return}
  l.innerHTML='';extractedQuestions.forEach(q=>{
    const d=document.createElement('div');d.style.cssText='padding:.6rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm);display:flex;justify-content:space-between;align-items:center';
    const escapeHtml = (unsafe) => (unsafe ?? '').toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    d.innerHTML=`<div style="flex:1"><strong style="color:var(--accent);font-size:.75rem">${escapeHtml(q.question_id)}</strong>
      <div class="text-secondary" style="font-size:.75rem;margin-top:.15rem">${escapeHtml(q.question_text)}</div></div>
      <button onclick="deleteQuestion('${escapeHtml(q.question_id)}')" class="btn btn-danger" style="padding:.2rem;background:transparent;border:none;margin-left:.5rem"><svg class="icon-sm"><use href="#ico-x"/></svg></button>`;
    l.appendChild(d);
  });
}

function renderCoordsList(){
  const l=document.getElementById('mappedCoordsList');if(!l)return;
  const coords=Object.values(coordMap);
  if(!coords.length){l.innerHTML='<span class="text-muted" style="font-size:.75rem">No coordinates mapped yet.</span>';return}
  l.innerHTML='';coords.forEach(c=>{
    const d=document.createElement('div');d.style.cssText='padding:.4rem .6rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm);display:flex;justify-content:space-between;align-items:center';
    d.innerHTML=`<span style="font-weight:600;font-size:.75rem;color:var(--text-primary)">${escapeHtml(c.question_id)}</span><span style="display:flex;gap:.4rem;align-items:center"><span class="badge badge-info" style="font-size:.6rem">${escapeHtml(c.max_score||10)} pts</span><span class="badge badge-success" style="font-size:.6rem">Mapped</span></span>`;
    l.appendChild(d);
  });
}

function updateCanvasZoom(delta){
    const c=gc(); if(!c) return;
    const currentW = c.offsetWidth;
    const newW = Math.max(400, Math.min(3000, currentW + (delta * 100)));
    c.style.width = newW + 'px';
}

[qCanvas, aCanvas].forEach(c => {
    if(!c) return;
    c.addEventListener('wheel', e => {
        if(e.ctrlKey) {
            e.preventDefault();
            updateCanvasZoom(e.deltaY < 0 ? 1 : -1);
        }
    });
});

async function previewCrop(source){
  if(!sessionId||!currentSelection){notify('Draw a crop box first.','warning');return null}
  const m=c2o(currentSelection);
  const payload={source,page_index:source==='question'?+(document.getElementById('questionPageIndex')?.value||0):+(document.getElementById('answerPageIndex')?.value||0),
    sheet_index:source==='answer'?+(document.getElementById('answerSheetIndex')?.value||0):0,...m,clean:true};
  try{
    const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/crop/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    const url=`data:image/png;base64,${escapeHtml(d.preview_base64)}`;
    if(source==='question'){document.getElementById('questionCropPreview').src=url;document.getElementById('questionCropPreview').style.display='block';document.getElementById('questionCropPlaceholder').style.display='none'}
    else{document.getElementById('answerCropPreview').src=url;document.getElementById('answerCropPreview').style.display='block';document.getElementById('answerCropPlaceholder').style.display='none'}
    return{mapped:d.crop_box,dataUrl:url};
  }catch(err){notify(err.message,'error');return null}
}

// Canvas mouse
function onDown(e){const c=gc(),r=c.getBoundingClientRect();startPoint={x:e.clientX-r.left,y:e.clientY-r.top};isDragging=true}
function onMove(e){
  if(!isDragging||!startPoint)return;
  const c=gc(), r=c.getBoundingClientRect();
  const x=e.clientX-r.left, y=e.clientY-r.top;
  const scaleX = c.width / r.width;
  const scaleY = c.height / r.height;
  const sx = startPoint.x * scaleX, sy = startPoint.y * scaleY;
  const cx = x * scaleX, cy = y * scaleY;
  currentSelection={x:Math.min(sx,cx), y:Math.min(sy,cy), w:Math.abs(cx-sx), h:Math.abs(cy-sy)};
  drawPreview();
}
function onUp(){if(!isDragging)return;isDragging=false;if(currentSelection&&currentSelection.w<8)currentSelection=null;drawPreview()}
if(qCanvas){qCanvas.addEventListener('mousedown',onDown);qCanvas.addEventListener('mousemove',onMove)}
if(aCanvas){aCanvas.addEventListener('mousedown',onDown);aCanvas.addEventListener('mousemove',onMove)}
window.addEventListener('mouseup',onUp);

// Load previews
document.getElementById('loadQuestionPreview')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('Create a session first.','warning');activeCanvasKind='question';
  const pi=+(document.getElementById('questionPageIndex')?.value||0);
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/preview?source=question&page_index=${escapeHtml(pi)}`);if(!r.ok) { const errData = await r.json(); throw new Error(typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)); }
    const b=await r.blob();qImg.onload=()=>{const cw=qCanvas.parentElement.clientWidth;qCanvas.width=cw;qCanvas.height=Math.round(qImg.naturalHeight*(cw/qImg.naturalWidth));currentSelection=null;drawPreview()};
    qImg.src=URL.createObjectURL(b)}catch(err){notify(err.message,'error')}});

document.getElementById('loadAnswerPreview')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('Create a session first.','warning');activeCanvasKind='answer';
  const si=+(document.getElementById('answerSheetIndex')?.value||0),pi=+(document.getElementById('answerPageIndex')?.value||0);
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/preview?source=answer&sheet_index=${escapeHtml(si)}&page_index=${escapeHtml(pi)}`);if(!r.ok) { const errData = await r.json(); throw new Error(typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)); }
    const b=await r.blob();aImg.onload=()=>{const cw=aCanvas.parentElement.clientWidth;aCanvas.width=cw;aCanvas.height=Math.round(aImg.naturalHeight*(cw/aImg.naturalWidth));currentSelection=null;drawPreview()};
    aImg.src=URL.createObjectURL(b)}catch(err){notify(err.message,'error')}});

document.getElementById('previewQuestionCrop')?.addEventListener('click',()=>previewCrop('question'));
document.getElementById('previewAnswerCrop')?.addEventListener('click',()=>previewCrop('answer'));

document.getElementById('extractQuestion')?.addEventListener('click',async()=>{
  if(!sessionId||!currentSelection)return notify('Draw a crop box first.','warning');
  const btn=document.getElementById('extractQuestion');btn.textContent='Extracting…';btn.disabled=true;
  try{const pv=await previewCrop('question');if(!pv)throw new Error('Preview failed');
    const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/questions/from-crop`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({page_index:+(document.getElementById('questionPageIndex')?.value||0),...pv.mapped})});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    extractedQuestions=d.questions||[];renderQPicker();renderQList();populateRubricQuestionPicker();notify(`Extracted ${escapeHtml(d.question.question_id)}`,'success');currentSelection=null;drawPreview();
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Extract Question Text';btn.disabled=false}});

document.getElementById('useSelection')?.addEventListener('click',async()=>{
  const pk=document.getElementById('questionPicker');
  if(!currentSelection||!pk?.value)return notify('Select a question and draw a crop.','warning');
  try{const pv=await previewCrop('answer');if(!pv)return;
    const ms=parseFloat(document.getElementById('questionMaxScore')?.value)||10;
    coordMap[pk.value]={question_id:pk.value,question_text:(extractedQuestions.find(q=>q.question_id===pk.value)||{}).question_text||'',
      page_index:+(document.getElementById('answerPageIndex')?.value||0),...pv.mapped,marking_scheme:null,max_score:ms};
    renderCoordsList();notify(`Mapped ${escapeHtml(pk.value)}`,'success');currentSelection=null;drawPreview();pk.value='';
  }catch(err){notify(err.message,'error')}});

document.getElementById('saveCoords')?.addEventListener('click',async()=>{
  if(!sessionId)return;const coords=Object.values(coordMap);if(!coords.length)return notify('No coordinates.','warning');
  const btn=document.getElementById('saveCoords');btn.textContent='Saving…';btn.disabled=true;
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/coordinates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({coordinates:coords})});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);notify('Coordinates saved!','success');markStep('nav-crop',true);
  }catch(err){notify(err.message,'error')}finally{btn.textContent='Save Coordinate Templates';btn.disabled=false}});

// ─── Pipeline Animations ───
function createCompletionBurst(stepEl){
  const indicator=stepEl.querySelector('.step-indicator');
  if(!indicator)return;
  const rect=indicator.getBoundingClientRect();
  const cx=rect.left+rect.width/2,cy=rect.top+rect.height/2;
  for(let i=0;i<10;i++){
    const angle=(i/10)*Math.PI*2+(Math.random()-.5)*.3;
    const dist=25+Math.random()*20;
    const p=document.createElement('div');
    p.className='burst-particle';
    p.style.left=cx+'px';p.style.top=cy+'px';
    p.style.setProperty('--bx',Math.cos(angle)*dist+'px');
    p.style.setProperty('--by',Math.sin(angle)*dist+'px');
    p.style.animationDelay=Math.random()*.08+'s';
    document.body.appendChild(p);
    p.addEventListener('animationend',()=>p.remove());
  }
}

// ─── Pipeline ───
function startPipelineTimer(){
  pipelineStartTime=Date.now();
  const el=document.getElementById('pipelineTimer');
  if(el)el.style.display='';
  pipelineTimerInterval=setInterval(()=>{
    const elapsed=Math.floor((Date.now()-pipelineStartTime)/1000);
    const m=String(Math.floor(elapsed/60)).padStart(2,'0');
    const s=String(elapsed%60).padStart(2,'0');
    if(el)el.textContent=`${escapeHtml(m)}:${escapeHtml(s)}`;
  },1000);
}
function stopPipelineTimer(){
  if(pipelineTimerInterval){clearInterval(pipelineTimerInterval);pipelineTimerInterval=null}
}

document.getElementById('runGrading')?.addEventListener('click',async()=>{
  if(!sessionId)return notify('No session.','warning');
  const btn=document.getElementById('runGrading');btn.disabled=true;btn.textContent='Starting…';
  const steps=document.querySelectorAll('.pipeline-step');const statusText=document.getElementById('pipelineStatusText');const stepsContainer=document.getElementById('pipelineSteps');
  statusText.classList.remove('hidden');statusText.textContent='Starting pipeline…';
  startPipelineTimer();
  document.title='Running Pipeline... | GradeOps Vision';
  stepsContainer?.classList.add('pipeline-running');
  try{
    const r=await fetch(`/api/exams/${sessionId}/run`,{method:'POST'});
    const d=await r.json();if(!r.ok)throw new Error(d.detail);
    const jobId=d.job_id;
    btn.textContent='Running…';
    const stepMap={rubrics:1,grading:2,plagiarism:3};
    let prevStepIdx=-1;
    const pollInterval=setInterval(async()=>{
      try{
        const pr=await fetch(`/api/exams/${sessionId}/job/${jobId}`);
        const pj=await pr.json();
        if(pj.step){
          const si=stepMap[pj.step]||0;
          if(si>prevStepIdx&&prevStepIdx>=0)createCompletionBurst(steps[prevStepIdx]);
          prevStepIdx=si;
          steps.forEach((s,i)=>{s.classList.toggle('active',i===si);s.classList.toggle('done',i<si)});
        }
        if(pj.total>0)statusText.textContent=`Processing ${pj.progress}/${pj.total}…`;
        if(pj.status==='done'){
          clearInterval(pollInterval);stopPipelineTimer();
          stepsContainer?.classList.remove('pipeline-running');
          steps.forEach((s,i)=>{const wasDone=s.classList.contains('done');s.classList.remove('active');s.classList.add('done');if(!wasDone)setTimeout(()=>createCompletionBurst(s),i*120)});
          const elapsed=Math.floor((Date.now()-pipelineStartTime)/1000);
          const sm=pj.summary||{};
          statusText.textContent=`Done in ${elapsed}s! ${sm.graded_entries||0} graded, ${sm.review_required||0} need review.`;
          notify('Pipeline complete!','success');markStep('nav-pipeline',true);
          await fetchDashboard();
          setTimeout(()=>switchView('view-results'),1500);
          btn.disabled=false;btn.textContent='Run Grading Pipeline';
        } else if(pj.status==='failed'){
          clearInterval(pollInterval);stopPipelineTimer();
          stepsContainer?.classList.remove('pipeline-running');
          steps.forEach(s=>{s.classList.remove('active','done')});
          notify(pj.error||'Pipeline failed','error');statusText.textContent='Pipeline failed.';
          btn.disabled=false;btn.textContent='Run Grading Pipeline';
        }
      }catch(pe){clearInterval(pollInterval);stopPipelineTimer();stepsContainer?.classList.remove('pipeline-running');notify('Polling error','error');btn.disabled=false;btn.textContent='Run Grading Pipeline'}
    },2000);
  }catch(err){stopPipelineTimer();stepsContainer?.classList.remove('pipeline-running');steps.forEach(s=>{s.classList.remove('active','done')});notify(err.message,'error');statusText.textContent='Pipeline failed.';btn.disabled=false;btn.textContent='Run Grading Pipeline'}
});

// ─── Dashboard Data ───
async function fetchDashboard(){
  if(!sessionId)return notify('No session.','warning');
  try{const r=await fetch(`/api/exams/${escapeHtml(sessionId)}/dashboard`);const d=await r.json();if(!r.ok)throw new Error(d.detail);
    dashData=d;allResults=d.results||[];reviewQueue=d.review_queue||[];rIdx=0;
    
    // Populate reviewStatuses from loaded data
    reviewStatuses={};
    reviewQueue.forEach((item, index) => {
      if (item.review_status && item.review_status !== 'pending') {
        reviewStatuses[index] = item.review_status;
      }
    });

    renderStats(d.analytics);renderScoreDistribution(allResults);
    renderErrorDist(d.analytics?.error_distribution);renderRubrics(d.analytics?.rubrics);
    renderQuestionAnalytics(allResults);
    renderResultsTable(allResults);renderReviewUI();renderPlagiarism(d.plagiarism_flags);
    markStep('nav-results',true);
  }catch(err){notify(err.message,'error')}}
document.getElementById('loadDashboard')?.addEventListener('click',fetchDashboard);

function renderStats(a){
  if(!a)return;
  animateCounter('statTotal', a.total_graded);
  animateCounter('statAvgScore', parseFloat(a.avg_score), 1);
  animateCounter('statAvgAccuracy', Math.round(a.avg_accuracy*100), 0, '%');
  animateCounter('statReview', a.review_count);
  animateCounter('statPlagiarism', a.plagiarism_count);
  const pb=document.getElementById('plagiarismBadge');
  if(pb)pb.textContent=`${escapeHtml(a.plagiarism_count)} flags`;
}

function renderScoreDistribution(results){
  const card=document.getElementById('scoreDistCard'),container=document.getElementById('scoreHistogram');
  if(!results?.length){if(card)card.style.display='none';return}
  if(card)card.style.display='';
  const scores=results.map(r=>r.proposed_score||0);
  const maxScore=Math.max(...scores,10);
  const bucketSize=Math.max(1,Math.ceil(maxScore/6));
  const buckets=[];
  for(let i=0;i<maxScore;i+=bucketSize){
    const lo=i,hi=Math.min(i+bucketSize,maxScore);
    const count=scores.filter(s=>s>=lo&&(hi===maxScore?s<=hi:s<hi)).length;
    buckets.push({label:`${lo}-${hi}`,count});
  }
  const maxCount=Math.max(...buckets.map(b=>b.count),1);
  container.innerHTML='';
  buckets.forEach(b=>{
    const pct=Math.round(b.count/maxCount*100);
    container.innerHTML+=`<div class="histogram-bar-group">
      <div class="histogram-bar" style="height:${Math.max(pct,4)}%"><span class="bar-tooltip">${b.count} student${escapeHtml(b.count!==1?'s':'')}</span></div>
      <span class="histogram-label">${b.label}</span></div>`;
  });
}

function renderQuestionAnalytics(results){
  const card=document.getElementById('questionAnalyticsCard'),grid=document.getElementById('questionAnalyticsGrid');
  if(!results?.length){if(card)card.style.display='none';return}
  const byQ={};
  results.forEach(r=>{
    const qid=r.question_id||'unknown';
    if(!byQ[qid])byQ[qid]={scores:[],errors:{},maxScore:r.rubric?.max_score||10};
    byQ[qid].scores.push(r.proposed_score||0);
    (r.error_axes||[]).forEach(e=>{const label=typeof e==='string'?e:String(e);byQ[qid].errors[label]=(byQ[qid].errors[label]||0)+1});
  });
  if(!Object.keys(byQ).length){if(card)card.style.display='none';return}
  card.style.display='';grid.innerHTML='';
  const errColors={computational:'var(--warning)',conceptual:'var(--danger)',notation:'var(--info)',presentation:'var(--success)'};
  Object.entries(byQ).forEach(([qid,data])=>{
    const avg=data.scores.length?data.scores.reduce((a,b)=>a+b,0)/data.scores.length:0;
    const min=Math.min(...data.scores);
    const max=Math.max(...data.scores);
    const pct=data.maxScore>0?Math.round(avg/data.maxScore*100):0;
    let errHtml='';
    const totalErrors=Object.values(data.errors).reduce((a,b)=>a+b,0)||1;
    Object.entries(data.errors).forEach(([k,v])=>{
      const ePct=Math.round(v/totalErrors*100);
      errHtml+=`<div class="q-analytics-bar">
        <span style="min-width:80px;color:var(--text-muted);text-transform:capitalize">${k}</span>
        <div class="q-analytics-bar-track"><div class="q-analytics-bar-fill" style="width:${ePct}%;background:${escapeHtml(errColors[k]||'var(--accent)')}"></div></div>
        <span style="color:var(--text-primary);font-weight:700">${v}</span></div>`;
    });
    if(!errHtml)errHtml='<span class="text-muted" style="font-size:.75rem">No errors recorded</span>';
    grid.innerHTML+=`<div class="q-analytics-card">
      <div class="q-analytics-header">
        <span class="badge badge-info">${qid.toUpperCase()}</span>
        <div class="q-analytics-score">${avg.toFixed(1)}<span style="font-size:.75rem;font-weight:500;color:var(--text-muted)"> / ${data.maxScore}</span></div>
      </div>
      <div class="progress-bar" style="margin-bottom:.75rem"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:.6875rem;color:var(--text-muted);margin-bottom:.75rem">
        <span>Min: ${min.toFixed(1)}</span><span>${data.scores.length} graded</span><span>Max: ${max.toFixed(1)}</span>
      </div>
      ${errHtml}</div>`;
  });
}

function renderErrorDist(dist){
  const card=document.getElementById('errorDistCard'),container=document.getElementById('errorDistBars');
  if(!dist||!Object.keys(dist).length){card.style.display='none';return}
  card.style.display='';container.innerHTML='';
  const max=Math.max(...Object.values(dist),1);
  const colors={computational:'var(--warning)',conceptual:'var(--danger)',notation:'var(--info)',presentation:'var(--success)'};
  Object.entries(dist).forEach(([k,v])=>{
    const pct=Math.round(v/max*100);
    container.innerHTML+=`<div style="display:flex;align-items:center;gap:.75rem">
      <span style="min-width:100px;font-size:.75rem;font-weight:600;color:var(--text-secondary);text-transform:capitalize">${k}</span>
      <div class="progress-bar" style="flex:1"><div class="progress-fill" style="width:${pct}%;background:${escapeHtml(colors[k]||'var(--accent)')}"></div></div>
      <span style="font-size:.75rem;font-weight:700;color:var(--text-primary);min-width:24px;text-align:right">${v}</span></div>`;
  });
}

function renderRubrics(rubrics){ console.log("renderRubrics called with: ", rubrics);
  const card=document.getElementById('rubricViewerCard'),sel=document.getElementById('rubricQSelect'),detail=document.getElementById('rubricDetail'),badge=document.getElementById('rubricCountBadge');
  if(!rubrics||!Object.keys(rubrics).length){if(card)card.style.display='none';return}
  
  // Explicitly show the card if rubrics exist
  if(card){
    card.style.display='block';
    card.classList.remove('hidden');
  }

  const qids=Object.keys(rubrics);
  if(badge)badge.textContent=`${escapeHtml(qids.length)} rubric${escapeHtml(qids.length!==1?'s':'')}`;
  if(!sel||!detail)return;
  sel.innerHTML='';
  qids.forEach(qid=>{const o=document.createElement('option');o.value=qid;o.textContent=qid.toUpperCase();sel.appendChild(o)});
  function show(qid){
    const rb=rubrics[qid];if(!rb){detail.innerHTML='<p class="text-muted">No rubric data.</p>';return}
    let html=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <span class="badge badge-info" style="font-family: monospace; font-size: 1rem;">${escapeHtml(rb.question_id||qid)}</span><span style="font-size:1rem;font-weight:700;color:var(--accent)">Max Score: ${escapeHtml(rb.max_score||10)} pts</span></div>`;
    
    if (rb.criteria && rb.criteria.length > 0) {
      rb.criteria.forEach(c=>{
        html+=`<div class="criteria-item" style="padding: 0.8rem; border-left: 3px solid var(--accent); margin-bottom: 0.5rem; background: var(--bg-surface); border-radius: 4px;">
          <span class="criteria-desc" style="display: block; font-size: 0.95rem; margin-bottom: 0.3rem;">${escapeHtml(c.description)}</span>
          <span class="criteria-pts" style="display: inline-block; font-size: 0.8rem; font-weight: bold; background: var(--accent-dim); color: var(--accent); padding: 0.2rem 0.5rem; border-radius: 4px;">${escapeHtml(c.points)} pts</span>
        </div>`;
      });
    } else {
      html+=`<div class="criteria-item" style="padding: 1rem; text-align: center; background: var(--bg-surface); border-radius: 8px; border: 1px dashed var(--border-color);">
        <span class="criteria-desc text-muted">Criteria structure not detailed in DB. Showing only total max score.</span>
      </div>`;
    }
    detail.innerHTML=html;
  }
  sel.onchange=()=>show(sel.value);show(sel.value);
}

function renderResultsTable(results){
  const tb=document.getElementById('resultsTableBody');
  if(!tb)return;
  if(!results?.length){tb.innerHTML='<tr><td colspan="6" class="text-muted text-center" style="padding:2rem">No results.</td></tr>';return}
  tb.innerHTML='';
  
  results.forEach((r,idx)=>{
    const acc=r.accuracy!=null?Math.round(r.accuracy*100)+'%':'—';
    const accClass=r.accuracy>=.8?'badge-success':r.accuracy>=.6?'badge-warning':'badge-danger';
    const errors=(r.error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'—';
    const needsReview=r.needs_review?'<span class="badge badge-danger">Yes</span>':'<span class="badge badge-success">No</span>';
    const flagged=r.accuracy<.7||r.needs_review;
    
    const row=document.createElement('tr');
    row.className=`expandable ${escapeHtml(flagged?'row-flagged':'')}`;
    row.dataset.idx=idx;
    row.innerHTML=`<td>${escapeHtml(r.student_id||'—')}</td><td>${escapeHtml(r.question_id||'—')}</td>
      <td style="font-weight:700">${escapeHtml(r.proposed_score??'—')}</td><td><span class="badge ${escapeHtml(accClass)}">${escapeHtml(acc)}</span></td>
      <td>${errors}</td><td>${needsReview}</td>`;
    
    const detailRow=document.createElement('tr');
    detailRow.className='detail-row';
    detailRow.dataset.detail=idx;
    detailRow.innerHTML=`<td colspan="6">
        <div class="detail-content">
          <div class="detail-section"><h5>AI Justification</h5><p>${escapeHtml((r.justification||'No justification provided.').replace(/\n/g,'<br>'))}</p></div>
          <div class="detail-section"><h5>OCR Transcription</h5><p>${escapeHtml((r.transcription||'No transcription.').replace(/\n/g,'<br>'))}</p></div>
        </div></td>`;
    
    row.addEventListener('click',()=>{
      row.classList.toggle('expanded');
      detailRow.classList.toggle('visible');
    });
    
    tb.appendChild(row);
    tb.appendChild(detailRow);
  });
}

// ─── Search & Filter ───
document.getElementById('resultsSearch')?.addEventListener('input',e=>{filterResults()});
document.getElementById('resultsFilter')?.addEventListener('change',e=>{filterResults()});
function filterResults(){
  const query=(document.getElementById('resultsSearch')?.value||'').toLowerCase();
  const filter=document.getElementById('resultsFilter')?.value||'all';
  let filtered=allResults;
  if(query){
    filtered=filtered.filter(r=>
      (r.student_id||'').toLowerCase().includes(query)||
      (r.question_id||'').toLowerCase().includes(query)||
      (r.justification||'').toLowerCase().includes(query)
    );
  }
  if(filter==='review')filtered=filtered.filter(r=>r.needs_review||r.accuracy<.7);
  if(filter==='good')filtered=filtered.filter(r=>!r.needs_review&&r.accuracy>=.7);
  renderResultsTable(filtered);
}

// ─── CSV Export ───
document.getElementById('exportCSV')?.addEventListener('click',()=>{
  if(!allResults?.length)return notify('No results to export.','warning');
  const headers=['Student ID','Question ID','Score','Accuracy','Errors','Needs Review','Justification','Transcription'];
  const rows=allResults.map(r=>[
    r.student_id||'',r.question_id||'',r.proposed_score??'',
    r.accuracy!=null?Math.round(r.accuracy*100)+'%':'',
    (r.error_axes||[]).join('; '),r.needs_review?'Yes':'No',
    `"${escapeHtml((r.justification||'').replace(/"/g,'""'))}"`,
    `"${escapeHtml((r.transcription||'').replace(/"/g,'""'))}"`
  ]);
  const csv=[headers.join(','),...rows.map(r=>r.join(','))].join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=`gradeops_results_${escapeHtml(sessionId||'export')}.csv`;a.click();
  URL.revokeObjectURL(url);
  notify('CSV exported!','success');
});


// ─── PDF Report Export ───
document.getElementById('exportReport')?.addEventListener('click', () => {
  if(!sessionId) return notify('No session to export.', 'warning');
  window.open(`/api/exams/${sessionId}/report`, '_blank');
});

// ─── Review ───
function renderReviewUI(){
  document.getElementById('reviewCountBadge').textContent=`${escapeHtml(reviewQueue.length)} items`;
  if(reviewQueue.length){document.getElementById('reviewWorkspace').classList.remove('hidden');document.getElementById('reviewEmptyState').classList.add('hidden');updateReviewProgress();renderReviewItem()}
  else{document.getElementById('reviewWorkspace').classList.add('hidden');document.getElementById('reviewEmptyState').classList.remove('hidden')}
}

function updateReviewProgress(){
  const reviewed=Object.keys(reviewStatuses).length;
  const total=reviewQueue.length;
  const pct=total>0?Math.round(reviewed/total*100):0;
  const el=document.getElementById('reviewProgressText');if(el)el.textContent=`${escapeHtml(reviewed)} / ${escapeHtml(total)} reviewed`;
  const fill=document.getElementById('reviewProgressFill');if(fill)fill.style.width=`${pct}%`;
}

function renderReviewItem(){
  if(!reviewQueue.length||rIdx<0||rIdx>=reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  document.getElementById('reviewCounter').textContent=`${escapeHtml(rIdx+1)} / ${escapeHtml(reviewQueue.length)}`;
  document.getElementById('reviewStudentId').textContent=`Student: ${escapeHtml(item.student_id)}`;
  document.getElementById('reviewQuestionId').textContent=`Q: ${escapeHtml(item.question_id)}`;
  if(item.snippet_path){
    const fn=item.snippet_path.replace(/\\/g,'/').split('/').pop();
    document.getElementById('reviewCropImg').src=`/api/storage/${escapeHtml(fn)}`;
    document.getElementById('reviewCropImg').style.display='block';
  } else {
    document.getElementById('reviewCropImg').style.display='none';
  }
  document.getElementById('reviewTranscription').textContent=item.transcription||'[Empty]';
  document.getElementById('reviewScore').textContent=item.proposed_score??'—';
  document.getElementById('reviewMaxPoints').textContent=item.rubric?.max_score??'—';
  const axes=document.getElementById('reviewErrorAxes');
  if(axes)axes.innerHTML=(item.error_axes||[]).map(a=>`<span class="error-tag ${escapeHtml(a)}">${escapeHtml(a)}</span>`).join('')||'<span class="text-muted" style="font-size:.75rem">No errors.</span>';
  document.getElementById('reviewJustification').innerHTML=item.justification?item.justification.replace(/\n/g,'<br>'):'<span class="text-muted">No justification.</span>';
  const ab=document.getElementById('reviewAccuracyBadge');
  if(ab){const acc=Math.round((item.accuracy||0)*100);ab.textContent=`${escapeHtml(acc)}% Match`;ab.className=`badge ${escapeHtml(acc<70?'badge-warning':'badge-success')}`}
  const statusEl=document.getElementById('reviewCurrentStatus');
  const status=reviewStatuses[rIdx];
  if(status==='approved'){statusEl.className='review-status-indicator approved';statusEl.textContent='Approved'}
  else if(status==='overridden'){statusEl.className='review-status-indicator overridden';statusEl.textContent='Overridden'}
  else{statusEl.className='review-status-indicator pending';statusEl.textContent='Pending'}
}

function reviewNext(){if(rIdx<reviewQueue.length-1){rIdx++;renderReviewItem()}else notify('End of queue.','info')}
function reviewPrev(){if(rIdx>0){rIdx--;renderReviewItem()}}
function approveCurrent(){
  if(!reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  const btn = document.getElementById('btnApprove');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  fetch(`/api/exams/${escapeHtml(sessionId)}/review/${escapeHtml(item.id)}`,{
    method:'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'approved' })
  })
    .then(r=>{if(!r.ok)throw new Error('Failed to persist approval');return r.json()})
    .then(()=>{
      reviewStatuses[rIdx]='approved';
      updateReviewProgress();
      notify(`Approved ${escapeHtml(rIdx+1)}/${escapeHtml(reviewQueue.length)}`,'success');
      renderReviewItem();
      if(rIdx<reviewQueue.length-1)setTimeout(()=>reviewNext(),300);
    }).catch(err=>notify(err.message,'error'))
    .finally(()=>{
      btn.disabled = false;
      btn.innerHTML = '<svg class="icon-sm"><use href="#ico-check"/></svg> Approve (A)';
    });
}
function overrideCurrent(){
  if(!reviewQueue.length)return;
  const item=reviewQueue[rIdx];
  const ns=prompt(`New score (max ${escapeHtml(item.rubric?.max_score||'?')}):`,item.proposed_score);
  if(ns!==null&&!isNaN(ns)){
    const newScore=parseFloat(ns);
    const btn = document.getElementById('btnOverride');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    fetch(`/api/exams/${escapeHtml(sessionId)}/review/${escapeHtml(item.id)}`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status: 'overridden', new_score:newScore})
    }).then(r=>{if(!r.ok)throw new Error('Failed to persist override');return r.json()})
      .then(()=>{
        item.proposed_score=newScore;
        reviewStatuses[rIdx]='overridden';
        updateReviewProgress();
        notify(`Overridden ${escapeHtml(rIdx+1)}/${escapeHtml(reviewQueue.length)}`,'success');
        renderReviewItem();

        const mainResult = allResults.find(r => r.id === item.id);
        if(mainResult) mainResult.proposed_score = newScore;
        filterResults();

        if(rIdx<reviewQueue.length-1)setTimeout(()=>reviewNext(),300);
      }).catch(err=>notify(err.message,'error'))
      .finally(()=>{
        btn.disabled = false;
        btn.innerHTML = '<svg class="icon-sm"><use href="#ico-edit"/></svg> Override (O)';
      });
  }
}
document.getElementById('btnNext')?.addEventListener('click',reviewNext);
document.getElementById('btnPrev')?.addEventListener('click',reviewPrev);
document.getElementById('btnApprove')?.addEventListener('click',approveCurrent);
document.getElementById('btnOverride')?.addEventListener('click',overrideCurrent);

function regradeCurrent(){
  if(!reviewQueue.length||!sessionId)return;
  const item=reviewQueue[rIdx];
  const btn=document.getElementById('btnRegrade');
  if(!confirm(`Re-grade ${item.student_id} / ${item.question_id}? This will re-run OCR and AI grading.`))return;
  btn.disabled=true;btn.textContent='Re-grading…';
  fetch(`/api/exams/${sessionId}/regrade/${item.id}`,{method:'POST'})
    .then(r=>{if(!r.ok)throw new Error('Re-grade failed');return r.json()})
    .then(d=>{
      const updated=d.result;
      if(updated){
        item.proposed_score=updated.proposed_score;
        item.justification=updated.justification;
        item.transcription=updated.transcription;
        item.error_axes=updated.error_axes||[];
        item.accuracy=updated.accuracy;
        item.needs_review=updated.needs_review;
        delete reviewStatuses[rIdx];
      }
      updateReviewProgress();renderReviewItem();
      notify('Re-grade complete','success');
      const mainResult=allResults.find(r=>r.id===item.id);
      if(mainResult&&updated){Object.assign(mainResult,updated)}
      filterResults();
    }).catch(err=>notify(err.message,'error'))
    .finally(()=>{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-refresh"/></svg> Re-grade (R)'});
}
document.getElementById('btnRegrade')?.addEventListener('click',regradeCurrent);

// ─── Plagiarism ───
function renderPlagiarism(flags){
  const container=document.getElementById('plagiarismList');
  if(!container)return;
  if(!flags?.length){
    container.innerHTML='<div class="card" style="text-align:center;padding:3rem"><p class="text-muted">No plagiarism data detected.</p></div>';
    return;
  }
  container.innerHTML='';
  flags.forEach(f=>{
    const p1=f.pair[0],p2=f.pair[1];
    const conf=Math.round(f.confidence*100);
    const errs=(f.shared_error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'None';
    container.innerHTML+=`<div class="plagiarism-item">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
        <div style="display:flex;align-items:center;gap:.75rem"><span class="badge badge-info">${escapeHtml(p1)}</span><span style="color:var(--text-muted)">↔</span><span class="badge badge-info">${escapeHtml(p2)}</span></div>
        <div class="accuracy-circle" style="width:40px;height:40px;font-size:.75rem;background:rgba(239,68,68,.1);border-color:var(--danger);color:var(--danger)">${escapeHtml(conf)}%</div>
      </div>
      <div style="margin-bottom:.5rem;font-size:.8125rem"><strong style="color:var(--text-secondary)">Reason:</strong> ${escapeHtml(f.reason)}</div>
      <div style="font-size:.8125rem"><strong style="color:var(--text-secondary)">Shared Errors:</strong> ${errs}</div></div>`;
  });
}

// ─── Sandbox ───
let selectedPreset='math';
function updateSandboxUI(){
  document.querySelectorAll('.sandbox-preset').forEach(p=>{
    const isSelected = p.id === `preset-${escapeHtml(selectedPreset)}`;
    p.classList.toggle('active', isSelected);
  });
  const customCard = document.getElementById('preset-custom');
  if(customCard){
    customCard.style.opacity = selectedPreset==='custom' ? '1' : '0.65';
  }
}

document.querySelectorAll('.sandbox-preset').forEach(p=>{
  p.addEventListener('click',()=>{
    selectedPreset=p.id.replace('preset-','');
    updateSandboxUI();
  });
});
updateSandboxUI();

document.getElementById('runSandbox')?.addEventListener('click', async () => {
  const btn = document.getElementById('runSandbox');
  btn.disabled = true;
  btn.textContent = 'Generating...';

  const status = document.getElementById('sandboxStatusText');
  document.getElementById('sandboxStatus').classList.remove('hidden');
  status.textContent = 'GENERATING DATA';

  try {
    const body = { preset: selectedPreset };
    if (selectedPreset === 'custom') {
      body.students = parseInt(document.getElementById('sandboxStudents')?.value) || 10;
      body.questions = parseInt(document.getElementById('sandboxQuestions')?.value) || 4;
      body.max_score = parseInt(document.getElementById('sandboxMaxScore')?.value) || 10;
      body.include_plagiarism = document.getElementById('sandboxPlagiarism')?.checked ?? true;
      body.include_low_conf = document.getElementById('sandboxLowConf')?.checked ?? true;
    }
    const r = await fetch('/api/sandbox/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail);

    sessionId = d.session_id;
    status.textContent = `Loaded ${escapeHtml(selectedPreset)} Preset: ${escapeHtml(sessionId)}`;
    status.style.color = '#10b981';
    notify(`${escapeHtml(selectedPreset)} sandbox generated!`, 'success');

    await fetchDashboard();
    setTimeout(() => switchView('view-results'), 1200);
  } catch(err) {
    status.textContent = 'FAILED';
    status.style.color = '#ef4444';
    notify(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate & Load';
  }
});

// ─── Rubric Editor ───
function populateRubricQuestionPicker(){
  const sel=document.getElementById('rubricQuestionPicker');if(!sel)return;
  sel.innerHTML='<option value="" disabled selected>Select question...</option>';
  extractedQuestions.forEach(q=>{
    const o=document.createElement('option');o.value=q.question_id;
    o.textContent=`${q.question_id}: ${q.question_text.slice(0,40)}…`;sel.appendChild(o);
  });
}

function addCriterionRow(desc='',pts='',type='conceptual'){
  const container=document.getElementById('criteriaRows');if(!container)return;
  const row=document.createElement('div');
  row.style.cssText='display:flex;gap:.5rem;align-items:center';
  row.innerHTML=`<input type="text" placeholder="Criterion description" value="${escapeHtml(desc)}" class="form-control criterion-desc" style="flex:2;font-size:.8rem">
    <input type="number" min="0" step="0.5" placeholder="Pts" value="${escapeHtml(pts)}" class="form-control criterion-pts" style="width:70px;font-size:.8rem">
    <select class="form-control criterion-type" style="width:130px;font-size:.8rem">
      <option value="conceptual"${type==='conceptual'?' selected':''}>Conceptual</option>
      <option value="computational"${type==='computational'?' selected':''}>Computational</option>
      <option value="notation"${type==='notation'?' selected':''}>Notation</option>
      <option value="presentation"${type==='presentation'?' selected':''}>Presentation</option>
    </select>
    <button class="btn btn-danger" style="padding:.2rem .4rem;background:transparent;border:none" onclick="this.parentElement.remove()"><svg class="icon-sm"><use href="#ico-x"/></svg></button>`;
  container.appendChild(row);
}

document.getElementById('addCriterionBtn')?.addEventListener('click',()=>addCriterionRow());

function collectRubricForm(){
  const qid=document.getElementById('rubricQuestionPicker')?.value;
  const maxScore=parseFloat(document.getElementById('rubricMaxScore')?.value)||10;
  if(!qid){notify('Select a question first.','warning');return null}
  const rows=document.querySelectorAll('#criteriaRows > div');
  const criteria=[];
  rows.forEach(row=>{
    const desc=row.querySelector('.criterion-desc')?.value?.trim();
    const pts=parseFloat(row.querySelector('.criterion-pts')?.value)||0;
    const type=row.querySelector('.criterion-type')?.value||'conceptual';
    if(desc)criteria.push({description:desc,points:pts,type});
  });
  if(!criteria.length){notify('Add at least one criterion.','warning');return null}
  return {question_id:qid,max_score:maxScore,criteria};
}

document.getElementById('saveRubricBtn')?.addEventListener('click',async()=>{
  const payload=collectRubricForm();if(!payload)return;
  if(!sessionId){notify('No active session.','warning');return}
  const btn=document.getElementById('saveRubricBtn');btn.disabled=true;btn.textContent='Saving…';
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to save rubric');
    notify(`Rubric saved for ${payload.question_id}`,'success');
    await loadSavedRubrics();
  }catch(err){notify(err.message,'error')}
  finally{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-save"/></svg> Save Rubric'}
});

document.getElementById('aiGenerateRubricBtn')?.addEventListener('click',async()=>{
  const qid=document.getElementById('rubricQuestionPicker')?.value;
  if(!qid){notify('Select a question first.','warning');return}
  if(!sessionId){notify('No active session.','warning');return}
  const btn=document.getElementById('aiGenerateRubricBtn');btn.disabled=true;btn.textContent='Generating…';
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics/${qid}/generate`,{method:'POST'});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to generate rubric');
    const rubric=d.rubric;
    document.getElementById('rubricMaxScore').value=rubric.max_score||10;
    document.getElementById('criteriaRows').innerHTML='';
    (rubric.criteria||[]).forEach(c=>addCriterionRow(c.description,c.points,c.type||'conceptual'));
    notify('AI rubric generated — review and save.','success');
  }catch(err){notify(err.message,'error')}
  finally{btn.disabled=false;btn.innerHTML='<svg class="icon-sm"><use href="#ico-zap"/></svg> AI Generate'}
});

async function loadSavedRubrics(){
  if(!sessionId)return;
  try{
    const r=await fetch(`/api/exams/${sessionId}/rubrics`);
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'Failed to load rubrics');
    renderSavedRubrics(d.rubrics||[]);
  }catch(err){notify(err.message,'error')}
}

function renderSavedRubrics(rubrics){
  const list=document.getElementById('savedRubricsList');
  const badge=document.getElementById('rubricEditorCount');
  const entries=Array.isArray(rubrics)?rubrics:Object.entries(rubrics||{}).map(([qid,rb])=>({question_id:qid,rubric_json:rb}));
  if(badge)badge.textContent=`${entries.length} rubric${entries.length!==1?'s':''} saved`;
  if(!list)return;
  if(!entries.length){list.innerHTML='<span class="text-muted" style="font-size:.75rem">No rubrics saved yet.</span>';return}
  list.innerHTML='';
  entries.forEach(r=>{
    const rb=r.rubric_json||{};
    const criteriaCount=(rb.criteria||[]).length;
    const card=document.createElement('div');
    card.style.cssText='padding:.75rem;background:var(--bg-base);border:1px solid var(--border-color);border-radius:var(--radius-sm)';
    card.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem">
      <span class="badge badge-info">${escapeHtml(r.question_id)}</span>
      <span style="font-size:.75rem;color:var(--text-muted)">${escapeHtml(rb.max_score||'?')} pts · ${escapeHtml(criteriaCount)} criteria</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:.25rem;margin-bottom:.5rem">
      ${(rb.criteria||[]).map(c=>`<div style="font-size:.75rem;color:var(--text-secondary);padding-left:.5rem;border-left:2px solid var(--accent)">
        ${escapeHtml(c.description)} <span style="font-weight:700">(${escapeHtml(c.points)} pts)</span></div>`).join('')}
    </div>
    <div style="display:flex;gap:.4rem">
      <button class="btn btn-secondary rubric-edit-btn" data-qid="${escapeHtml(r.question_id)}" style="padding:.2rem .5rem;font-size:.7rem">Edit</button>
      <button class="btn btn-danger rubric-delete-btn" data-qid="${escapeHtml(r.question_id)}" style="padding:.2rem .5rem;font-size:.7rem;background:transparent;border:1px solid var(--danger);color:var(--danger)">Delete</button>
    </div>`;
    card.querySelector('.rubric-edit-btn').addEventListener('click',()=>{
      document.getElementById('rubricQuestionPicker').value=r.question_id;
      document.getElementById('rubricMaxScore').value=rb.max_score||10;
      document.getElementById('criteriaRows').innerHTML='';
      (rb.criteria||[]).forEach(c=>addCriterionRow(c.description,c.points,c.type||'conceptual'));
    });
    card.querySelector('.rubric-delete-btn').addEventListener('click',async()=>{
      if(!confirm(`Delete rubric for ${r.question_id}?`))return;
      try{
        const res=await fetch(`/api/exams/${sessionId}/rubrics/${r.question_id}`,{method:'DELETE'});
        if(!res.ok)throw new Error('Delete failed');
        notify(`Rubric for ${r.question_id} deleted`,'info');
        await loadSavedRubrics();
      }catch(err){notify(err.message,'error')}
    });
    list.appendChild(card);
  });
}

document.getElementById('refreshRubricsBtn')?.addEventListener('click',loadSavedRubrics);

// ─── Keyboard Shortcuts ───
window.addEventListener('keydown',e=>{
  const active=document.querySelector('.view-section:not(.hidden)');
  if(active?.id==='view-review'&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'){
    if(e.key==='ArrowRight')reviewNext();if(e.key==='ArrowLeft')reviewPrev();
    if(e.key.toLowerCase()==='a')approveCurrent();if(e.key.toLowerCase()==='o'){e.preventDefault();overrideCurrent()}
    if(e.key.toLowerCase()==='r'){e.preventDefault();regradeCurrent()}}
});

// ─── Drag & Drop ───
['dz-qp','dz-as'].forEach(id=>{
  const dz=document.getElementById(id);if(!dz)return;
  dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('dragover')});
  dz.addEventListener('dragleave',()=>dz.classList.remove('dragover'));
  dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('dragover');
    const input=dz.querySelector('input[type=file]');if(input&&e.dataTransfer.files.length){input.files=e.dataTransfer.files;
      const labelId=input.id==='file-qp'?'label-qp':'label-as';updateFileName(input,labelId,input.multiple)}});
});

// ─── Student Reports ───
function renderStudentReports(filter=''){
  const container=document.getElementById('studentReportsList');
  const badge=document.getElementById('studentCountBadge');
  if(!container)return;
  if(!allResults?.length){
    container.innerHTML='<div class="card" style="text-align:center;padding:3rem"><p class="text-muted">No grading results available. Run the pipeline first.</p></div>';
    if(badge)badge.textContent='0 students';
    return;
  }
  const byStudent={};
  allResults.forEach(r=>{
    const sid=r.student_id||'Unknown';
    if(!byStudent[sid])byStudent[sid]={results:[],totalScore:0,totalMax:0,errors:{}};
    const s=byStudent[sid];
    s.results.push(r);
    s.totalScore+=r.proposed_score||0;
    s.totalMax+=(r.rubric?.max_score||10);
    (r.error_axes||[]).forEach(e=>{s.errors[e]=(s.errors[e]||0)+1});
  });

  let students=Object.entries(byStudent);
  if(filter){
    const q=filter.toLowerCase();
    students=students.filter(([sid])=>sid.toLowerCase().includes(q));
  }
  if(badge)badge.textContent=`${students.length} student${students.length!==1?'s':''}`;

  if(!students.length){container.innerHTML='<div class="card" style="text-align:center;padding:2rem"><p class="text-muted">No students match your search.</p></div>';return}

  container.innerHTML='';
  students.sort((a,b)=>a[0].localeCompare(b[0]));
  students.forEach(([sid,data])=>{
    const pct=data.totalMax>0?Math.round(data.totalScore/data.totalMax*100):0;
    const grade=pct>=90?'A+':pct>=80?'A':pct>=70?'B':pct>=60?'C':pct>=50?'D':'F';
    const gradeColor=pct>=70?'var(--success)':pct>=50?'var(--warning)':'var(--danger)';

    const errorEntries=Object.entries(data.errors).sort((a,b)=>b[1]-a[1]);
    const focusAreas=errorEntries.slice(0,3).map(([e,c])=>{
      const tips={
        conceptual:'Review core concepts and definitions',
        computational:'Practice numerical calculations and formulas',
        notation:'Pay attention to proper notation and symbols',
        presentation:'Improve answer structure and clarity',
        reasoning:'Strengthen logical reasoning and proof steps',
        formatting:'Follow required answer format guidelines'
      };
      return `<strong style="text-transform:capitalize">${escapeHtml(e)}</strong> (${c} issue${c>1?'s':''}): ${tips[e]||'Review this area'}`;
    });

    let qRows='';
    data.results.forEach(r=>{
      const max=r.rubric?.max_score||10;
      const qPct=max>0?Math.round((r.proposed_score||0)/max*100):0;
      const barColor=qPct>=70?'var(--success)':qPct>=50?'var(--warning)':'var(--danger)';
      const errs=(r.error_axes||[]).map(e=>`<span class="error-tag ${escapeHtml(e)}">${escapeHtml(e)}</span>`).join('')||'<span class="text-muted" style="font-size:.7rem">None</span>';
      qRows+=`<tr>
        <td style="font-weight:600">${escapeHtml(r.question_id||'—')}</td>
        <td><span style="font-weight:700">${r.proposed_score??'—'}</span><span class="text-muted"> / ${max}</span></td>
        <td><div class="progress-bar" style="width:80px;display:inline-flex"><div class="progress-fill" style="width:${qPct}%;background:${barColor}"></div></div> <span style="font-size:.7rem;font-weight:600">${qPct}%</span></td>
        <td>${errs}</td>
        <td style="font-size:.75rem;color:var(--text-secondary);max-width:300px;white-space:normal;line-height:1.4">${escapeHtml((r.justification||'—').slice(0,150))}${(r.justification||'').length>150?'…':''}</td>
      </tr>`;
    });

    const card=document.createElement('div');
    card.className='card';
    card.style.cssText='margin-bottom:1rem;padding:0;overflow:hidden';
    card.innerHTML=`
      <div style="display:flex;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid var(--border-color);cursor:pointer" class="student-report-header">
        <div style="display:flex;align-items:center;gap:1rem">
          <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent-secondary));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.8rem;color:#fff">${escapeHtml(sid.charAt(0).toUpperCase())}</div>
          <div>
            <div style="font-weight:700;font-size:.9375rem;color:var(--text-primary)">${escapeHtml(sid)}</div>
            <div style="font-size:.75rem;color:var(--text-muted)">${data.results.length} question${data.results.length!==1?'s':''} graded</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:1.25rem">
          <div style="text-align:right">
            <div style="font-size:.75rem;color:var(--text-muted)">Total Score</div>
            <div style="font-weight:800;font-size:1.1rem;color:var(--text-primary)">${data.totalScore.toFixed(1)} <span style="font-size:.75rem;font-weight:500;color:var(--text-muted)">/ ${data.totalMax}</span></div>
          </div>
          <div style="width:48px;height:48px;border-radius:50%;border:3px solid ${gradeColor};display:flex;align-items:center;justify-content:center;flex-direction:column">
            <span style="font-weight:800;font-size:.875rem;color:${gradeColor}">${grade}</span>
            <span style="font-size:.55rem;color:var(--text-muted)">${pct}%</span>
          </div>
        </div>
      </div>
      <div class="student-report-body" style="display:none;padding:1rem 1.25rem">
        <table class="data-table" style="margin-bottom:1rem">
          <thead><tr><th>Question</th><th>Score</th><th>Progress</th><th>Errors</th><th>Feedback</th></tr></thead>
          <tbody>${qRows}</tbody>
        </table>
        ${errorEntries.length?`<div style="background:rgba(6,10,20,.4);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:1rem;margin-top:.75rem">
          <h4 style="font-size:.8125rem;margin-bottom:.6rem;color:var(--text-primary)">Areas to Focus On</h4>
          <ul style="margin:0;padding-left:1.25rem;list-style:disc">${focusAreas.map(f=>`<li style="font-size:.8125rem;color:var(--text-secondary);margin-bottom:.35rem;line-height:1.5">${f}</li>`).join('')}</ul>
        </div>`:'<p class="text-muted" style="font-size:.8125rem">No specific issues found — great work!</p>'}
        ${errorEntries.length?`<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem">${errorEntries.map(([e,c])=>`<span class="error-tag ${escapeHtml(e)}" style="font-size:.7rem">${escapeHtml(e)} x${c}</span>`).join('')}</div>`:''}
      </div>`;
    card.querySelector('.student-report-header').addEventListener('click',()=>{
      const body=card.querySelector('.student-report-body');
      body.style.display=body.style.display==='none'?'block':'none';
    });
    container.appendChild(card);
  });
}

document.getElementById('studentSearch')?.addEventListener('input',e=>{
  renderStudentReports(e.target.value);
});

// ─── Visual Enhancements ───

// 4. Animated Stat Counters
function animateCounter(elementId, target, decimals=0, suffix='') {
  const el=document.getElementById(elementId);
  if(!el) return;
  const targetNum=parseFloat(target)||0;
  if(targetNum===0){el.textContent='0'+suffix;return}
  const duration=1200;
  const startTime=performance.now();
  function tick(now){
    const elapsed=now-startTime;
    const progress=Math.min(elapsed/duration,1);
    const eased=1-Math.pow(1-progress,3);
    const current=targetNum*eased;
    el.textContent=current.toFixed(decimals)+suffix;
    if(progress<1)requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// 3. Staggered Entrance Animations
function staggerChildren(parent){
  if(!parent) return;
  const children=parent.querySelectorAll('.card, .stat-card, .stat-grid, .pipeline-steps, h2, .tab-bar, .table-toolbar, .review-nav, .review-progress, .analytics-grid');
  children.forEach((child,i)=>{
    child.classList.remove('cascade-child');
    child.style.animationDelay='';
    void child.offsetWidth;
    child.classList.add('cascade-child');
    child.style.animationDelay=`${i*70}ms`;
    child.addEventListener('animationend',()=>{
      child.classList.remove('cascade-child');
      child.style.animationDelay='';
    },{once:true});
  });
}

// 6. Floating Particle Dots (optimized)
function initParticles(){
  const canvas=document.getElementById('particleCanvas');
  if(!canvas||matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx=canvas.getContext('2d');
  const COUNT=22;
  let mouse={x:-1000,y:-1000};
  let running=true;

  function resize(){canvas.width=window.innerWidth;canvas.height=window.innerHeight}
  resize();
  window.addEventListener('resize',resize);
  document.addEventListener('mousemove',e=>{mouse.x=e.clientX;mouse.y=e.clientY},{passive:true});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){running=false}
    else{running=true;requestAnimationFrame(draw)}
  });

  const particles=[];
  for(let i=0;i<COUNT;i++){
    const r=Math.random()*2.2+0.6;
    const hue=160+Math.random()*30;
    const alpha=Math.random()*0.5+0.15;
    const size=Math.ceil((r+2)*4);
    const sprite=document.createElement('canvas');
    sprite.width=sprite.height=size;
    const sc=sprite.getContext('2d');
    const c=size/2;
    const g=sc.createRadialGradient(c,c,0,c,c,r*2);
    g.addColorStop(0,`hsla(${hue},70%,60%,${alpha})`);
    g.addColorStop(1,`hsla(${hue},70%,60%,0)`);
    sc.fillStyle=g;
    sc.fillRect(0,0,size,size);
    particles.push({
      x:Math.random()*canvas.width,y:Math.random()*canvas.height,
      vx:(Math.random()-0.5)*0.35,vy:(Math.random()-0.5)*0.35,
      r,alpha,hue,sprite,sz:size
    });
  }

  function draw(){
    if(!running)return;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    for(let i=0;i<particles.length;i++){
      const p=particles[i];
      p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x=canvas.width;if(p.x>canvas.width)p.x=0;
      if(p.y<0)p.y=canvas.height;if(p.y>canvas.height)p.y=0;
      const dx=mouse.x-p.x,dy=mouse.y-p.y;
      const md=Math.sqrt(dx*dx+dy*dy);
      const mi=md<200?1-md/200:0;
      if(mi>0.01){
        const dr=p.r+mi*2,da=p.alpha+mi*0.3;
        ctx.beginPath();ctx.arc(p.x,p.y,dr,0,Math.PI*2);
        const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,dr*2);
        g.addColorStop(0,`hsla(${p.hue},70%,60%,${da})`);
        g.addColorStop(1,`hsla(${p.hue},70%,60%,0)`);
        ctx.fillStyle=g;ctx.fill();
      } else {
        ctx.drawImage(p.sprite,p.x-p.sz/2,p.y-p.sz/2);
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}

// 8. Button Ripple Effect
document.addEventListener('click',e=>{
  const btn=e.target.closest('.btn');
  if(!btn) return;
  const rect=btn.getBoundingClientRect();
  const ripple=document.createElement('span');
  ripple.className='btn-ripple';
  const size=Math.max(rect.width,rect.height);
  ripple.style.width=ripple.style.height=size+'px';
  ripple.style.left=(e.clientX-rect.left-size/2)+'px';
  ripple.style.top=(e.clientY-rect.top-size/2)+'px';
  btn.appendChild(ripple);
  ripple.addEventListener('animationend',()=>ripple.remove());
});

// 9. Tab Title Updates
function updateTabTitle(viewId){
  const titles={
    'view-upload':'Upload','view-sandbox':'Sandbox','view-crop':'Cropping Studio',
    'view-pipeline':'Pipeline','view-rubrics':'Rubrics','view-results':'Results & Analytics',
    'view-review':'Review Queue','view-plagiarism':'Plagiarism','view-students':'Student Reports'
  };
  const section=titles[viewId]||'Dashboard';
  const status=sessionId?` [${sessionId.slice(0,8)}]`:'';
  document.title=`${section}${status} | GradeOps Vision`;
}

// Init visual enhancements
initParticles();
staggerChildren(document.querySelector('.view-section:not(.hidden)'));
>>>>>>> 15b1898f1ea7244db1b396e1e9d47837e0f8d22b
