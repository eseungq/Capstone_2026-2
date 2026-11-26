'use strict';
const $=id=>document.getElementById(id), names=['양품','불량품'];
const token=document.querySelector('meta[name="door-token"]').content;
let current=null,busy=false,offset=0,total=0,revision=0,activeController=null,historyTicket=0;
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'X-Door-Token':token,...options.headers}});const data=await response.json();if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);return data;}
function post(path,data,ctx){return api(path,{method:'POST',signal:ctx?.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
function controls(){ $('file').disabled=false; $('inspect').disabled=busy||!current||!!current.prediction; $('reviewFields').disabled=busy||!current?.prediction; $('cam').disabled=busy||!current?.prediction;$('target').disabled=busy;for(const el of document.querySelectorAll('#history button'))el.disabled=busy; $('refresh').disabled=busy;$('previous').disabled=busy||offset===0;$('next').disabled=busy||offset+50>=total;}
async function task(label,fn,replaceSelection=false){
 if(busy&&!replaceSelection)return;
 if(replaceSelection){revision++;activeController?.abort();}
 const mine=revision,controller=new AbortController();activeController=controller;
 const ctx={signal:controller.signal,isCurrent:()=>mine===revision};
 busy=true;message(label);controls();
 try{await fn(ctx);}catch(e){if(ctx.isCurrent()&&e.name!=='AbortError')message(e.message,true);}
 finally{if(ctx.isCurrent()){busy=false;if(activeController===controller)activeController=null;controls();}}
}
function clearCam(){ $('camImage').hidden=true;$('camImage').removeAttribute('src');$('camMeta').hidden=true;$('camInfo').textContent='';$('camMessage').textContent='버튼을 요청할 때만 Grad-CAM을 계산합니다.';}
function render(item){
 current=item;$('empty').hidden=!!item;$('original').hidden=!item;$('preview').removeAttribute('src');$('original').removeAttribute('href');
 $('filename').textContent=item?`${item.filename} · EXIF 보정 ${item.width}×${item.height} · ${item.id}`:'';
 if(item){$('preview').src=item.preview_url;$('original').href=item.original_url;}
 const p=item?.prediction;$('prediction').textContent=p?`모델 예측: ${names[p.predicted_class]}`:'검사를 실행하면 결과가 표시됩니다.';
 $('prediction').className='prediction'+(p?(p.predicted_class?' bad':' good'):'');$('details').hidden=!p;
 $('score').textContent=p?p.raw_defect_score.toPrecision(9):'';$('elapsed').textContent=p?`${p.processing_ms.toFixed(2)} ms`:'';
 $('timing').textContent=p?p.timing_scope:'';$('modelInfo').textContent=p?JSON.stringify({...p.model,inferred_at:item.inferred_at},null,2):'';
 $('workerStatus').textContent=item?(p?(!item.review?'작업자 미확인':item.review.judgment==='판단 보류'?'작업자 판단 보류':'작업자 확인 완료'):'검사 실행 대기'):'사진 업로드 대기';
 // Only a saved operator review can restore a selection. Never copy the model prediction.
 document.querySelectorAll('[name="judgment"]').forEach(e=>e.checked=item?.review?.judgment===e.value);
 $('note').value=item?.review?.note||'';$('reviewHistory').replaceChildren();
 for(const r of (item?.reviews||[])){const line=document.createElement('div');line.textContent=`${new Date(r.reviewed_at).toLocaleString('ko-KR')} · ${r.judgment} · ${r.note} (${r.actor})`;$('reviewHistory').append(line);}
 $('target').value=String(p?.predicted_class??1);clearCam();controls();
}
function sameRecord(ctx,ident,item){if(!ctx.isCurrent()||current?.id!==ident)return false;if(item.id!==ident)throw Error('응답의 검사 ID가 요청과 다릅니다. 결과를 표시하지 않았습니다.');return true;}
async function history(ctx){
 const ticket=++historyTicket,requestedOffset=offset;const data=await api(`/api/records?offset=${requestedOffset}`,{signal:ctx?.signal});
 if(ticket!==historyTicket||requestedOffset!==offset||(ctx&&!ctx.isCurrent()))return;
 total=data.total;$('history').replaceChildren();
 if(!data.items.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;td.textContent='아직 검사 이력이 없습니다.';tr.append(td);$('history').append(tr);}
 for(const r of data.items){const tr=document.createElement('tr');for(const text of [new Date(r.created_at).toLocaleString('ko-KR'),r.filename,r.prediction?names[r.prediction.predicted_class]:'검사 대기',r.review?.judgment||'미확인']){const td=document.createElement('td');td.textContent=text;tr.append(td);}
 const td=document.createElement('td'),button=document.createElement('button');button.textContent='상세 보기';
 button.onclick=()=>task('검사 이력 조회 중…',async ctx=>{render(null);const item=await api(`/api/records/${r.id}`,{signal:ctx.signal});if(!ctx.isCurrent())return;if(item.id!==r.id)throw Error('검사 ID가 일치하지 않습니다.');render(item);message('저장된 검사 이력을 불러왔습니다.');$('preview').scrollIntoView({behavior:'smooth',block:'center'});},true);
 td.append(button);tr.append(td);$('history').append(tr);}
 $('page').textContent=`${total}건 · ${Math.floor(offset/50)+1}페이지`;controls();
}
$('file').onchange=()=>{const file=$('file').files[0];if(!file)return;return task('사진 업로드 및 방향 보정 중…',async ctx=>{
 render(null);$('file').value='';if(file.size>40*1024*1024)throw Error('파일은 최대 40MiB입니다.');
 const item=await api('/api/uploads',{method:'POST',signal:ctx.signal,headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
 if(!ctx.isCurrent())return;render(item);offset=0;await history(ctx);if(ctx.isCurrent())message('방향 보정 완료. 사진을 확인한 뒤 검사 실행을 누르세요.');
 },true);};
$('inspect').onclick=()=>task('GPU 검사 실행 중…',async ctx=>{const ident=current.id;const item=await post(`/api/records/${ident}/inspect`,{},ctx);if(!sameRecord(ctx,ident,item))return;render(item);await history(ctx);if(ctx.isCurrent())message('실제 GPU 추론 완료. 작업자 판단을 선택하고 저장하세요.');});
$('save').onclick=()=>task('작업자 판단 저장 중…',async ctx=>{const ident=current.id,judgment=document.querySelector('[name="judgment"]:checked')?.value;if(!judgment)throw Error('작업자 판단을 선택하세요.');const item=await post(`/api/records/${ident}/review`,{judgment,note:$('note').value},ctx);if(!sameRecord(ctx,ident,item))return;render(item);await history(ctx);if(ctx.isCurrent())message('작업자 판단을 저장했습니다. 원래 모델 예측은 보존됩니다.');});
$('cam').onclick=()=>task('선택 클래스의 판단 참고 영역 계산 중…',async ctx=>{
 const ident=current.id,cls=Number($('target').value);clearCam();
 const data=await post(`/api/records/${ident}/cam`,{target_class:cls},ctx);
 if(!ctx.isCurrent()||current?.id!==ident||Number($('target').value)!==cls)return;
 if((data.inspection_id!==undefined&&data.inspection_id!==ident)||data.target_class!==cls)throw Error('참고 영역 응답의 검사 ID 또는 클래스가 다릅니다. 표시하지 않았습니다.');
 if(data.overlay_url&&data.overlay_url!==`/assets/${ident}/cam${cls}.png`)throw Error('참고 영역 이미지의 검사 ID가 다릅니다.');
 $('camMessage').textContent=`검사 ${ident} · 설명 대상: ${names[cls]} logit · `+(data.constant?'유효한 양의 반응 없음 또는 일정한 맵. 색상 오버레이를 생성하지 않았습니다.':'판단 참고 영역을 표시합니다. 결함 위치 검출 결과가 아닙니다.');
 $('camImage').hidden=!data.overlay_url;if(data.overlay_url)$('camImage').src=data.overlay_url;$('camMeta').hidden=false;$('camInfo').textContent=JSON.stringify(data,null,2);message('판단 참고 영역 요청 완료.');
});
$('target').onchange=()=>{clearCam();$('camMessage').textContent=`선택 대상: ${names[Number($('target').value)]} logit. 버튼을 눌러 요청하세요.`;};
$('refresh').onclick=()=>task('이력 새로고침 중…',async ctx=>{await history(ctx);if(ctx.isCurrent())message('이력을 새로 불러왔습니다.');});
$('previous').onclick=()=>task('이력 조회 중…',async ctx=>{offset=Math.max(0,offset-50);await history(ctx);if(ctx.isCurrent())message('');});
$('next').onclick=()=>task('이력 조회 중…',async ctx=>{offset+=50;await history(ctx);if(ctx.isCurrent())message('');});
(async()=>{try{const health=await api('/api/health');$('health').textContent=health.ready?`${health.model.gpu} · FP32 준비됨`:'GPU 준비되지 않음';await history();}catch(e){message(e.message,true);$('health').textContent='서비스 연결 오류';}})();
