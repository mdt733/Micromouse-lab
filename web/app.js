import {Viewport} from './viewport.js';
const $=id=>document.getElementById(id);
const UI={config:null,editor:null,dirty:false,ws:null,history:[],lastT:-1,scene:null,running:false,canvasMode:'perspective',lastMessage:'',clearThrough:null,lastLogs:[],lastFrameAt:0,runId:-1,traceLen:1,complete:false,replay:null,replayMode:false,replayIndex:0,replayPlaying:false,replayTimer:0,replayPlayT:0,replayLoading:null,pendingSeek:null,configPending:false,pollBusy:false};
const viewport=new Viewport($('worldCanvas'),$('viewerMode'));
const groups=[
  {title:'CHASSIS & TYRES',fields:[
    ['mass_g','Total mass','g',15,150,1],['track_mm','Wheel track','mm',35,120,1],['wheel_radius_mm','Wheel radius','mm',5,30,.5],['grip','Tyre grip / μ','',.1,2,.05],['tire_stiffness','Slip stiffness','N/(m/s)',20,500,10]]},
  {title:'MOTOR & GEARBOX',fields:[
    ['motor_type','Motor type','select',['brushed','brushless','ideal']],['motor_kv','Motor Kv','rpm/V',500,12000,100],['gear_ratio','Gear ratio',':1',1,25,.5],['motor_resistance_ohm','Resistance','Ω',.1,15,.1],['motor_current_limit_a','Current limit','A',.1,5,.1],['motor_efficiency','Drive efficiency','',.3,1,.02]]},
  {title:'BATTERY & SUCTION',fields:[
    ['battery_v','Pack voltage','V',2,8.4,.1],['battery_internal_ohm','Internal resistance','Ω',0,.9,.01],['fan_force_n','Maximum suction','N',0,5,.05],['fan_time_constant_s','Fan response time','s',.01,.8,.01],['fan_max_w','Fan electrical load','W',0,25,.5]]},
  {title:'SENSORS & EXPERIMENT',fields:[
    ['sensor_noise_mm','ToF noise σ','mm',0,20,.2],['sensor_range_mm','ToF max range','mm',80,1500,20],['duration_s','Run duration','s',1,60,1],['seed','Random seed','',0,100000,1]]}
];
function toast(message,error=false){const el=$('toast');el.textContent=message;el.className='visible'+(error?' error':'');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className='',4300)}
async function api(url,options={}){const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const data=await response.json();if(!response.ok)throw Error(data.detail||data.error||'Server error');return data}
function num(x,places=2){return Number.isFinite(x)?Number(x).toFixed(places):'—'}
function parameterUI(config){
  $('courseSelect').value=config.course;
  $('parameterGroups').innerHTML='';
  for(const group of groups){
    const section=document.createElement('section');section.className='parameter-group';
    const heading=document.createElement('div');heading.className='group-title';heading.innerHTML=`${group.title} <span>⌄</span>`;section.append(heading);
    for(const [key,label,unit,min,max,step] of group.fields){
      const field=document.createElement('div');field.className='field';
      const labelRow=document.createElement('div');labelRow.className='field-head';
      const title=document.createElement('span');title.className='field-name';title.textContent=label;
      const value=document.createElement('span');value.className='field-value';value.id='val-'+key;labelRow.append(title,value);field.append(labelRow);
      const control=document.createElement(key==='motor_type'?'select':'input');control.id='param-'+key;control.dataset.key=key;
      if(key==='motor_type'){
        control.className='config-select';
        for(const name of min){const option=document.createElement('option');option.value=name;option.textContent=name[0].toUpperCase()+name.slice(1);control.append(option)}
        control.value=config[key];
        control.addEventListener('change',()=>{value.textContent=control.value;markPending()});
      }else{
        control.type='range';control.min=min;control.max=max;control.step=step;control.value=config[key];
        control.addEventListener('input',()=>{value.textContent=pretty(control.value,unit);markPending()});
      }
      value.textContent=key==='motor_type'?config[key]:pretty(config[key],unit);
      field.append(control);section.append(field);
    }
    $('parameterGroups').append(section);
  }
}
function pretty(value,unit){const n=Number(value);return (Number.isInteger(n)?n:n.toFixed(2))+(unit?' '+unit:'')}
function markPending(){UI.configPending=true;$('configStatus').textContent='Unapplied changes';$('configStatus').style.color='#f0d092'}
function currentConfig(){const c={...UI.config,course:$('courseSelect').value};for(const g of groups){for(const [key] of g.fields){const el=$('param-'+key);c[key]=key==='motor_type'?el.value:Number(el.value)}}return c}
function codeValue(){return UI.editor?UI.editor.getValue():$('codeEditor').value}
function setCodeValue(code){if(UI.editor)UI.editor.setValue(code);else $('codeEditor').value=code;UI.dirty=false;setDirty(false)}
function setDirty(flag){UI.dirty=flag;$('dirtyMarker').textContent=flag?'●':'';$('codeStatus').textContent=flag?'Unsaved code changes':'Code ready'}
async function saveCode(){await api('/api/controller',{method:'POST',body:JSON.stringify({code:codeValue()})});setDirty(false);toast('Controller source saved')}
async function act(action){
  try{
    if(action==='reset'){leaveReplay();UI.history=[];UI.lastT=-1;}
    const response=await api('/api/action',{method:'POST',body:JSON.stringify({action})});
    statusUpdate(response);
    return response;
  }catch(e){toast(e.message,true);throw e}
}
async function saveAndRun(){
  $('runButton').disabled=true;
  try{
    // Stop any existing controller before replacing source. Then rebuild only if necessary.
    await api('/api/action',{method:'POST',body:JSON.stringify({action:'pause'})});
    await api('/api/controller',{method:'POST',body:JSON.stringify({code:codeValue()})});
    setDirty(false);
    if(UI.configPending){
      const applied=await api('/api/config',{method:'POST',body:JSON.stringify({config:currentConfig()})});
      statusUpdate(applied);UI.configPending=false;
    }
    leaveReplay();UI.history=[];UI.lastT=-1;
    const reset=await api('/api/action',{method:'POST',body:JSON.stringify({action:'reset'})});statusUpdate(reset);
    const running=await api('/api/action',{method:'POST',body:JSON.stringify({action:'run'})});statusUpdate(running);
    toast('Run started · use the timeline to inspect recorded moments');
  }catch(e){toast(e.message,true)}finally{$('runButton').disabled=false}
}
function statusUpdate(data){
  if(data.scene){UI.scene=data.scene;viewport.update(data.scene,data.state);$('sceneName').textContent=data.scene.title;}
  if(data.config){UI.config=data.config;parameterUI(data.config);$('configStatus').textContent='Applied to physics';$('configStatus').style.color='';UI.configPending=false;}
  updateFrame(data)
}
function updateFrame(data){
  UI.lastFrameAt=Date.now();
  if(data.run_id!==undefined && data.run_id!==UI.runId){
    UI.runId=data.run_id;UI.history=[];UI.lastT=-1;
    leaveReplay();
  }
  if(data.running!==undefined){
    UI.running=data.running;UI.complete=Boolean(data.complete);
    $('runStatus').textContent=UI.replayMode?'REPLAY':data.running?'RUNNING':UI.complete?'COMPLETE':'PAUSED';
    $('runningLed').classList.toggle('running',data.running);
    $('codeStatus').textContent=UI.dirty?'Unsaved code changes':data.loaded?'Controller active':'Controller not loaded';
  }
  if(data.trace_len!==undefined)UI.traceLen=data.trace_len;
  if(data.state){
    if(!UI.replayMode){
      presentSnapshot(data.state,data.sensors);
      if(data.state.t<UI.lastT){UI.history=[];UI.lastT=-1}
      if(data.state.t!==UI.lastT){
        UI.history.push({t:data.state.t,speed:data.state.speed,grip:data.state.grip_use,accel:data.state.accel_ms2});
        if(UI.history.length>6000)UI.history.shift();UI.lastT=data.state.t;
      }
    }
    updateTimeline(data.state.t);
  }
  if(data.logs){
    UI.lastLogs=data.logs;
    if(!UI.replayMode)showLogs(data.logs);
  }
}
function presentSnapshot(s,sensor){
  viewport.update(null,s);
  $('valueTime').innerHTML=num(s.t,2)+' <small>s</small>';
  $('valueSpeed').innerHTML=num(s.speed,2)+' <small>m/s</small>';
  $('valueGrip').innerHTML=num((s.grip_use||0)*100,0)+' <small>%</small>';
  $('valueFan').innerHTML=num(s.fan_force_n,2)+' <small>N</small>';
  $('valueEnergy').innerHTML=num(s.energy_j,1)+' <small>J</small>';
  $('statusDetail').textContent=`Distance ${num(s.distance_m,2)} m · Collisions ${s.collisions} · Battery ${num(s.battery_v,2)} V`;
  $('replayReadouts').textContent=`Acceleration ${num(s.accel_ms2,2)} m/s² · Forward ${num(s.accel_forward_ms2,2)} · Lateral ${num(s.accel_lateral_ms2,2)} m/s² · Grip ${num((s.grip_use||0)*100,0)}% · Motor ${num((s.current_a||[])[0],2)} / ${num((s.current_a||[])[1],2)} A`;
  if(sensor){
    const tof=sensor.tof_mm||{};
    const names=[['FRONT','front'],['F-LEFT','front_left'],['F-RIGHT','front_right'],['LEFT','left'],['RIGHT','right']];
    $('sensorGrid').innerHTML=names.map(([label,key])=>`<div>${label}<strong>${tof[key]===null||tof[key]===undefined?'—':Math.round(tof[key])+' <small>mm</small>'}</strong></div>`).join('')+`<div>GYRO<strong>${num(sensor.gyro_z_rad_s,2)} <small>rad/s</small></strong></div>`;
  }
}
function showLogs(logs){
  let visibleLogs=logs;
  if(UI.clearThrough && !UI.replayMode){
    const index=logs.findLastIndex(entry=>(entry.t+'|'+entry.line)===UI.clearThrough);
    if(index>=0)visibleLogs=logs.slice(index+1);else UI.clearThrough=null;
  }
  const html=visibleLogs.slice(-350).map(entry=>`<div class="log-entry${/error|traceback|timeout/i.test(entry.line)?' error':''}"><span class="stamp">[${num(entry.t,2)}]</span>${escapeHTML(entry.line)}</div>`).join('');
  if(html!==UI.lastMessage){
    const el=$('console'),atBottom=el.scrollHeight-el.clientHeight-el.scrollTop<50;
    el.innerHTML=html;UI.lastMessage=html;
    if(atBottom)el.scrollTop=el.scrollHeight;
  }
}
function updateTimeline(t){
  const seek=$('replaySeek');
  seek.max=Math.max(1,UI.replayMode&&UI.replay?UI.replay.frames.length-1:UI.traceLen-1);
  seek.disabled=UI.traceLen<2;
  $('replayButton').disabled=UI.traceLen<2;
  $('replayPlayButton').disabled=UI.traceLen<2;
  if(!UI.replayMode){
    seek.value=seek.max;
    $('replayTimeLabel').textContent=`${num(t,2)} / ${num(t,2)} s`;
    $('replayModeLabel').textContent=UI.complete?'FINISHED · drag to inspect':'LIVE · 50 Hz recording';
  }
}
function leaveReplay(){
  UI.replayPlaying=false;UI.replayMode=false;UI.replay=null;UI.replayLoading=null;UI.pendingSeek=null;
  $('replayStrip').classList.remove('is-replay');
  $('replayPlayButton').textContent='▶ Replay';
  if(!UI.running)$('runStatus').textContent=UI.complete?'COMPLETE':'PAUSED';
  $('replayModeLabel').textContent='LIVE · 50 Hz recording';
  $('replayButton').textContent='Inspect';
  if(UI.lastLogs.length)showLogs(UI.lastLogs);
}
async function enterReplay(index){
  UI.pendingSeek=index;
  if(UI.replayMode && UI.replay){selectReplayFrame(index);return}
  if(UI.replayLoading)return UI.replayLoading;
  UI.replayLoading=(async()=>{
    await api('/api/action',{method:'POST',body:JSON.stringify({action:'pause'})});
    const record=await api('/api/replay');
    if(record.run_id!==UI.runId)throw Error('The run was reset while loading replay');
    if(!record.frames?.length)throw Error('No replay frames recorded yet');
    UI.replay=record;UI.replayMode=true;UI.replayPlaying=false;
    $('replayStrip').classList.add('is-replay');
    $('replayModeLabel').textContent='REPLAY · inspect recorded physics';
    $('replayButton').textContent='Inspecting';
    UI.running=false;$('runStatus').textContent='REPLAY';
    selectReplayFrame(UI.pendingSeek??(record.frames.length-1));
  })();
  try{await UI.replayLoading}catch(e){toast('Replay unavailable: '+e.message,true)}finally{UI.replayLoading=null}
}
function selectReplayFrame(index){
  if(!UI.replayMode||!UI.replay)return;
  const frames=UI.replay.frames;
  const n=Math.max(0,Math.min(frames.length-1,Math.round(index)));
  UI.replayIndex=n;
  const frame=frames[n];
  viewport.showReplayFrame(frame.state,frames,n);
  presentSnapshot(frame.state,frame.sensors);
  showLogs(UI.replay.logs.filter(e=>e.t<=frame.state.t));
  $('replaySeek').max=Math.max(1,frames.length-1);
  $('replaySeek').value=n;
  $('replayTimeLabel').textContent=`${num(frame.state.t,2)} / ${num(frames.at(-1).state.t,2)} s`;
}
function replayPlayback(timestamp){
  if(!UI.replayMode||!UI.replayPlaying||!UI.replay)return;
  if(!UI.replayTimer)UI.replayTimer=timestamp;
  const delta=Math.max(0,Math.min((timestamp-UI.replayTimer)/1000,.2));
  UI.replayTimer=timestamp;
  const frames=UI.replay.frames;
  UI.replayPlayT+=delta;
  let index=UI.replayIndex;
  while(index<frames.length-1 && frames[index+1].state.t<=UI.replayPlayT)index++;
  if(index!==UI.replayIndex)selectReplayFrame(index);
  if(index>=frames.length-1){UI.replayPlaying=false;$('replayPlayButton').textContent='▶ Replay'}
}
function escapeHTML(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')}
function connectWS(){
  const scheme=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(scheme+'//'+location.host+'/ws');UI.ws=ws;
  ws.onopen=()=>{$('connectionLed').classList.add('online');$('connectionLabel').textContent='Connected'};
  ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==='status'){statusUpdate(data)}else updateFrame(data)};
  ws.onclose=()=>{$('connectionLed').classList.remove('online');$('connectionLabel').textContent='Reconnecting';setTimeout(connectWS,1600)};
}
async function init(){
  const [data,controller]=await Promise.all([api('/api/status'),api('/api/controller')]);statusUpdate(data);setCodeValue(controller.code);
  connectWS();wireUp();initializeMonaco();
  // REST fallback also repairs an apparently frozen Run if WebSockets are blocked.
  setInterval(async()=>{if(UI.pollBusy||Date.now()-UI.lastFrameAt<350)return;UI.pollBusy=true;try{const frame=await api('/api/status');updateFrame(frame);$('connectionLabel').textContent='Connected · polling';$('connectionLed').classList.add('online')}catch(e){$('connectionLabel').textContent='Backend offline';$('connectionLed').classList.remove('online')}finally{UI.pollBusy=false}},400);
  requestAnimationFrame(render);
}
function render(timestamp){replayPlayback(timestamp);viewport.draw();if(!$('graph').hidden)drawGraph();requestAnimationFrame(render)}
function drawGraph(){const canvas=$('telemetryCanvas'),ctx=canvas.getContext('2d');if(!ctx)return;const w=canvas.clientWidth,h=canvas.clientHeight;if(w<4||h<4)return;
  const dpr=Math.min(devicePixelRatio,2);if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr)}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='#273c49';ctx.lineWidth=1;for(let i=0;i<5;i++){ctx.beginPath();ctx.moveTo(0,h*i/4);ctx.lineTo(w,h*i/4);ctx.stroke()}
  const values=UI.replayMode&&UI.replay?UI.replay.frames.map(f=>({t:f.state.t,speed:f.state.speed,grip:f.state.grip_use,accel:f.state.accel_ms2})):UI.history; if(values.length<2)return;const maxSpeed=Math.max(1.5,...values.map(x=>x.speed))*1.08;const maxAccel=Math.max(4,...values.map(x=>x.accel||0));
  for(const [key,denom,color] of [['speed',maxSpeed,'#64cadb'],['grip',1,'#b5e87d'],['accel',maxAccel,'#e8b86a']]){ctx.strokeStyle=color;ctx.lineWidth=1.8;ctx.beginPath();values.forEach((entry,i)=>{const x=i/Math.max(values.length-1,1)*w,y=h-4-Math.max(0,entry[key]/denom)*(h-10);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()}
  if(UI.replayMode){const x=UI.replayIndex/Math.max(values.length-1,1)*w;ctx.strokeStyle='#f5f4e5';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke()}
}
function wireUp(){
  $('runButton').addEventListener('click',saveAndRun);
  $('pauseButton').addEventListener('click',()=>act('pause').catch(()=>{}));
  $('stepButton').addEventListener('click',()=>{leaveReplay();act('step').catch(()=>{})});
  $('resetButton').addEventListener('click',()=>act('reset').catch(()=>{}));
  $('exportButton').addEventListener('click',()=>{location.href='/api/export'});
  $('saveButton').addEventListener('click',async()=>{try{await saveCode()}catch(e){toast(e.message,true)}});
  $('replaySeek').addEventListener('input',e=>{const i=Number(e.target.value);UI.replayPlaying=false;$('replayPlayButton').textContent='▶ Replay';enterReplay(i)});
  $('replayButton').addEventListener('click',()=>enterReplay(UI.traceLen-1));
  $('replayPlayButton').addEventListener('click',async()=>{if(!UI.replayMode)await enterReplay(0);if(!UI.replayMode)return;if(UI.replayIndex>=UI.replay.frames.length-1)selectReplayFrame(0);UI.replayPlaying=!UI.replayPlaying;UI.replayTimer=0;UI.replayPlayT=UI.replay.frames[UI.replayIndex].state.t;$('replayPlayButton').textContent=UI.replayPlaying?'Ⅱ Replay':'▶ Replay'});
  $('liveButton').addEventListener('click',async()=>{leaveReplay();try{updateFrame(await api('/api/status'))}catch(e){toast(e.message,true)}});
  $('exampleSelect').addEventListener('change',async e=>{if(!e.target.value)return;try{const result=await api('/api/examples/'+e.target.value);setCodeValue(result.code);setDirty(true);toast('Example loaded. Save & Run to execute it.')}catch(err){toast(err.message,true)}e.target.value=''});
  $('applyButton').addEventListener('click',async()=>{try{const data=await api('/api/config',{method:'POST',body:JSON.stringify({config:currentConfig()})});statusUpdate(data);toast('Hardware and course rebuilt')}catch(e){toast(e.message,true)}});
  $('courseSelect').addEventListener('change',markPending);
  $('codeEditor').addEventListener('input',()=>setDirty(true));
  $('codeEditor').addEventListener('keydown',e=>{if(e.key==='Tab'){e.preventDefault();const el=e.target;const start=el.selectionStart;el.setRangeText('    ',start,el.selectionEnd,'end')}});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveCode().catch(err=>toast(err.message,true))}});
  for(const btn of document.querySelectorAll('[data-camera]'))btn.addEventListener('click',()=>{viewport.cameraMode(btn.dataset.camera);for(const b of document.querySelectorAll('[data-camera]'))b.classList.toggle('selected',b===btn)});
  for(const btn of document.querySelectorAll('[data-mobile-panel]'))btn.addEventListener('click',()=>{for(const panel of ['garage','editor','world'])$(panel).classList.toggle('mobile-active',panel===btn.dataset.mobilePanel);for(const b of document.querySelectorAll('[data-mobile-panel]'))b.classList.toggle('selected',b===btn);viewport.resize()});
  $('world').classList.add('mobile-active');
  $('tabConsole').addEventListener('click',()=>setLowerTab('console'));
  $('tabGraph').addEventListener('click',()=>setLowerTab('graph'));
  $('clearConsole').addEventListener('click',()=>{const logs=UI.lastLogs;if(logs.length){const last=logs[logs.length-1];UI.clearThrough=last.t+'|'+last.line;} $('console').innerHTML='';UI.lastMessage='';});
  splitter($('splitterLeft'),'left');splitter($('splitterCenter'),'center');
}
function setLowerTab(which){$('console').hidden=which!=='console';$('graph').hidden=which!=='graph';$('tabConsole').classList.toggle('selected',which==='console');$('tabGraph').classList.toggle('selected',which==='graph')}
function splitter(element,which){let origin,initial;element.addEventListener('pointerdown',e=>{origin=e.clientX;initial=which==='left'?parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--left-width')):parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--center-width'));element.setPointerCapture(e.pointerId);element.classList.add('dragging')});element.addEventListener('pointermove',e=>{if(origin===undefined)return;const delta=e.clientX-origin;const next=Math.max(which==='left'?240:320,Math.min(which==='left'?600:750,initial+delta));document.documentElement.style.setProperty(which==='left'?'--left-width':'--center-width',next+'px')});const end=()=>{origin=undefined;element.classList.remove('dragging')};element.addEventListener('pointerup',end);element.addEventListener('pointercancel',end)}
function initializeMonaco(){
  let tries=0;
  function load(){if(!window.require){if(tries++<25)setTimeout(load,350);return}
    try{window.require.config({paths:{vs:'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.52.2/min/vs'}});
      window.require(['vs/editor/editor.main'],()=>{
        if(!window.monaco)return;
        const textarea=$('codeEditor'),value=textarea.value;textarea.style.display='none';
        UI.editor=window.monaco.editor.create($('editorContainer'),{value,language:'python',theme:'vs-dark',automaticLayout:true,minimap:{enabled:false},fontSize:12,lineNumbers:'on',scrollBeyondLastLine:false,wordWrap:'off',renderWhitespace:'selection',padding:{top:14},tabSize:4});
        UI.editor.onDidChangeModelContent(()=>setDirty(true));
        UI.editor.addCommand(window.monaco.KeyMod.CtrlCmd|window.monaco.KeyCode.KeyS,()=>saveCode().catch(e=>toast(e.message,true)));
        setDirty(false);
      },err=>console.warn('Monaco unavailable, textarea editor retained',err));
    }catch(e){console.warn('Monaco failed, using textarea',e)}
  }load();
}
init().catch(err=>{console.error(err);toast('Failed to contact Python backend: '+err.message,true)});
