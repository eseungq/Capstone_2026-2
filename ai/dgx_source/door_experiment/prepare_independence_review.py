"""Prioritize new-boundary evidence without editing trained manifests or originals."""
import csv,hashlib,html,json,math
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageFilter,ImageDraw
from ai_api.duplicate_groups import components
from ai_api.similarity_review_history import load_imports

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def pair(a,b):return tuple(sorted((a,b)))
def pixels(path):
    with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGB')
    rgb=im.resize((64,64),Image.Resampling.BILINEAR).tobytes()
    gray=im.convert('L').resize((64,64),Image.Resampling.BILINEAR)
    # Ignore border pixels of FIND_EDGES to avoid an artificial frame.
    edge=gray.filter(ImageFilter.FIND_EDGES).crop((1,1,63,63)).tobytes()
    return dict(rgb=rgb,edge=edge,size=im.size,sha256=sha(path))
def main():
    root=Path(__file__).resolve().parents[1];pointer=load(root/'outputs/door_independence/latest.json');audit=root/pointer['directory'];confirmation=root/pointer['confirmationDirectory']
    proposal=load(root/'ai_api/verification/latest_data_proposal.json');group_dir=root/proposal['groupDirectory'];groups=load(group_dir/'groups.json');ids=[g['groupId'] for g in groups];byid={g['groupId']:g for g in groups}
    review=load(confirmation/'user_confirmation.json')
    if sha(review['source'])!=review['sourceSHA256']:raise ValueError('Example ordering changed')
    for r in review['records']:
        if sha(r['validation_image'])!=r['source_file_sha256']['validation'] or sha(r['train_image'])!=r['source_file_sha256']['train']:raise ValueError('Confirmed source changed')
    merges=[(r['validation_group'],r['train_group']) for r in review['records'] if r['judgment']=='user_confirmed_same_photo']
    out=root/'outputs/door_independence_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);print('[NEW REVIEW OUTPUT]',out,flush=True)
    updated=[];old_to_new={}
    for comp in components(ids,merges):
        members=sorted({p for gid in comp for p in byid[gid]['members']});gid='door_'+hashlib.sha256('\n'.join(members).encode()).hexdigest()
        classes=sorted({c for old in comp for c in byid[old]['classIds']});old_splits=sorted({s for old in comp for s in byid[old]['originalSplits']})
        updated.append(dict(groupId=gid,members=members,classIds=classes,labelConflict=len(classes)>1,originalSplits=old_splits,action='hold_for_label_resolution' if len(classes)>1 else 'keep_group_in_one_future_split'))
        for old in comp:old_to_new[old]=gid
    dump(out/'future_groups.json',updated);dump(out/'old_to_future_group.json',old_to_new)
    membership={path:g['groupId'] for g in groups for path in g['members']}
    history={};sources=[root/'ai_api/verification/similarity_rank_20261016T183911_041173Z/user_similarity_review.json',root/'ai_api/verification/split_candidate_20261017T044724_629801Z/user_similarity_review_round2.json']
    for source in sources:
        data=load(source)
        if sha(data['source'])!=data['sourceSHA256']:raise ValueError('Historical ordering changed')
        for r in data['records']:history[pair(r['validation_image'],r['train_image'])]=r['judgment']
    imports=[root/'outputs/door_remaining_review_import/20261027T185447_467114Z/summary.json',*[root/p for p in proposal.get('additionalSimilarityReviewImports',[])]]
    imported,import_hashes=load_imports(imports)
    for (a,b),value in imported.items():history[pair(a,b)]=value['decision']
    for r in review['records']:history[pair(r['validation_image'],r['train_image'])]=r['judgment']
    reviewed_group_pairs={pair(old_to_new[membership[a]],old_to_new[membership[b]]) for a,b in history}
    # Broader suspected-part units only reduce repetitive review scheduling, never label propagation.
    suspect=load(root/proposal['suspectedPartConstraintFile']);unit_edges=[tuple(old_to_new[g] for g in c['duplicateGroupIds']) for c in suspect]
    unit_map={}
    for comp in components([g['groupId'] for g in updated],unit_edges):
        unit='unit_'+hashlib.sha256('\n'.join(comp).encode()).hexdigest()
        for gid in comp:unit_map[gid]=unit
    raw=load(audit/'visual_candidates.json');remaining=[];excluded=Counter()
    for r in raw:
        a,b=r['model_selection_image'],r['train_image'];ga,gb=old_to_new[membership[a]],old_to_new[membership[b]]
        if ga==gb:excluded['confirmed_same_photo_group']+=1;continue
        if unit_map[ga]==unit_map[gb]:excluded['known_suspected_part_unit']+=1;continue
        if pair(a,b) in history or pair(ga,gb) in reviewed_group_pairs:excluded['previous_review_record']+=1;continue
        remaining.append(dict(r,validation_image=a,validationGroup=ga,trainGroup=gb,validationReviewUnit=unit_map[ga],trainReviewUnit=unit_map[gb]))
    # Bound original decoding, cover multiple validation groups rather than all near-flat pairs.
    pool=[];per_valid=Counter();per_train=Counter()
    for r in sorted(remaining,key=lambda r:(not r['outside_previous_search'],r['distance'],r['model_selection_image'],r['train_image'])):
        if per_valid[r['validationReviewUnit']]>=2 or per_train[r['trainReviewUnit']]>=4:continue
        pool.append(r);per_valid[r['validationReviewUnit']]+=1;per_train[r['trainReviewUnit']]+=1
        if len(pool)==160:break
    paths=sorted({r[k] for r in pool for k in ['validation_image','train_image']})
    verified={r['image_path']:r['sha256'] for r in load(audit/'current_file_hashes.json')}
    evidence={}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i,(path,result) in enumerate(zip(paths,executor.map(pixels,paths)),1):
            if result['sha256']!=verified[path]:raise ValueError('Image changed since independence audit')
            evidence[path]=result
            if i%50==0 or i==len(paths):print('[PAIR PIXEL FEATURES]',i,'/',len(paths),flush=True)
    for r in pool:
        a,b=evidence[r['validation_image']],evidence[r['train_image']]
        rgb=sum(abs(x-y) for x,y in zip(a['rgb'],b['rgb']))/len(a['rgb']);edge=sum(abs(x-y) for x,y in zip(a['edge'],b['edge']))/len(a['edge']);energy=(sum(a['edge'])+sum(b['edge']))/(2*len(a['edge']))
        aspect=abs(math.log((a['size'][0]/a['size'][1])/(b['size'][0]/b['size'][1])))
        r.update(rgbMAE64=rgb,edgeMAE64=edge,edgeEnergy64=energy,aspectDifference=aspect,rankScore=rgb/255+edge/max(energy,1)+aspect+r['distance']/64)
    selected=[];used=set()
    for r in sorted(pool,key=lambda r:(r['rankScore'],r['distance'],r['validation_image'],r['train_image'])):
        ends={r['validationReviewUnit'],r['trainReviewUnit']}
        if used & ends:continue
        selected.append(r);used.update(ends)
        if len(selected)==10:break
    assert len(selected)==10 and len(used)==20
    for i,r in enumerate(selected,1):
        r.update(caseId=f'candidate_{i:02d}',priorityReason='현재 학습/모델 선택 경계 · 이전 미검색 범위 우선 · 구도/픽셀 특징 재정렬',proposalRoles=['model_selection','train'])
        assert pair(r['validation_image'],r['train_image']) not in history
    dump(out/'review_queue.json',selected);dump(out/'bounded_ranked_candidates.json',sorted(pool,key=lambda r:r['rankScore']));dump(out/'review_history_reused.json',[dict(paths=list(k),decision=v) for k,v in history.items()])
    cards=[];contact=Image.new('RGB',(1000,220*len(selected)),'white');draw=ImageDraw.Draw(contact)
    for i,r in enumerate(selected):
        cards.append(f'<article><h2>새 차수 {i+1}번</h2><p>왼쪽: 현재 모델 선택 / 오른쪽: 현재 학습. 이전 예시6·8번과 다른 번호입니다.</p><div class="pair">')
        draw.text((8,i*220+4),f'NEW {i+1}: selection / train',fill='black')
        for j,key in enumerate(['validation_image','train_image']):
            name=f'pair_{i+1:02d}_{j}.jpg'
            with Image.open(r[key]) as im:preview=ImageOps.exif_transpose(im).convert('RGB')
            preview.thumbnail((760,560));preview.save(out/name,quality=92);preview.thumbnail((490,185));contact.paste(preview,(j*500,i*220+25))
            cards.append(f'<a target="_blank" href="{html.escape(Path(r[key]).as_uri(),quote=True)}"><img src="{name}"></a>')
        cards.append(f'</div><label>判断 <select id="decision_{i}"><option value="UNREVIEWED">미검토</option><option value="SAME_PHOTO">같은 사진</option><option value="POSSIBLY_SAME_PART">같은 실물·다른 촬영 의심</option><option value="DIFFERENT">다른 사진·동일 실물 근거 없음</option><option value="UNSURE">판단 불가</option></select></label><textarea id="reason_{i}" placeholder="구별 근거를 짧게 적어주세요"></textarea></article>'.replace('判断','판단'))
    contact.save(out/'contact_sheet.jpg',quality=92)
    template=(root/'ai_api/similarity_priority_template.html').read_text();start=template.index('<p>왼쪽은');end=template.index('</p>',start)+4
    template=template[:start]+'<p>왼쪽은 현재 모델 선택, 오른쪽은 현재 학습 사진입니다. 이전 예시8쌍과 별도의 새10쌍입니다. 원본을 눌러 확인할 수 있습니다. 유사도는 동일 사진 확정값이 아닙니다.</p>'+template[end:]
    page=template.replace('__CARDS__','\n'.join(cards)).replace('__COUNT__',str(len(selected))).replace('__QUEUE_JSON__',json.dumps(selected,ensure_ascii=True).replace('<','\\u003c')).replace('__QUEUE_SHA_JSON__',json.dumps(sha(out/'review_queue.json')))
    (out/'index.html').write_text(page)
    summary=dict(status='next_review_prepared_no_resplit_or_retraining',original_group_count=len(groups),future_group_count=len(updated),confirmed_group_merges=len(merges),current_split_applied=False,review_history_pairs=len(history),source_candidate_pairs=len(raw),excluded=dict(excluded),eligible_pairs=len(remaining),bounded_pixel_rank_pairs=len(pool),pixel_feature_images=len(paths),selected_pairs=len(selected),selected_new_search_scope_pairs=sum(r['outside_previous_search'] for r in selected),final_test_read=False,reserved_images_read=False,originals_modified=False,model_changed=False,training_started=False,independence_established=False,source_sha256={str(p):sha(p) for p in [audit/'visual_candidates.json',group_dir/'groups.json',confirmation/'user_confirmation.json',*sources,*imports,Path(__file__).resolve()]},import_history_hashes=import_hashes,limitations=['Bounded 160-pair ranking, not exhaustive RGB/pixel comparison.','RGB/edge/geometry only prioritize review, not identity thresholds.','The trained model remains exposed to confirmed cross-role same photos.'])
    dump(out/'summary.json',summary);dump(root/'outputs/door_independence_review/latest.json',dict(directory=str(out),reviewPage=str(out/'index.html'),queue=str(out/'review_queue.json'),futureGroups=str(out/'future_groups.json'),independenceEstablished=False))
    print('[NEXT INDEPENDENCE REVIEW]',out/'index.html',flush=True);print(json.dumps({k:v for k,v in summary.items() if k not in ['source_sha256','import_history_hashes']},ensure_ascii=False))
if __name__=='__main__':main()
