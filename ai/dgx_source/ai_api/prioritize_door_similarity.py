"""Compress review scheduling, not data: preserve all unresolved relations and inspect exact pixels."""
import argparse
import hashlib
import html
import json
from collections import Counter,defaultdict,deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ai_api.duplicate_groups import ROOT,read_csv


def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def priority(row):return (not row['proposedLabelDisagreement'],row['rankScore'],row['validation_image'],row['train_image'])

def distinct_pairs(rows):
    result=[];seen=set()
    for row in sorted(rows,key=priority):
        key=tuple(sorted((row['validationReviewUnit'],row['trainReviewUnit'])))
        if key not in seen:seen.add(key);result.append(row)
    return result

def select_diverse(rows,limit):
    # These units are scheduling constraints, not confirmed duplicate groups.
    selected=[];used=set()
    for risk in [True,False]:
        buckets=defaultdict(deque)
        for row in sorted(rows,key=priority):
            if row['proposedLabelDisagreement'] is risk:
                key=(tuple(sorted(row['proposalRoles'])),tuple(sorted(row['sourceCategories'])))
                buckets[key].append(row)
        keys=sorted(buckets,key=lambda key:priority(buckets[key][0]))
        progress=True
        while progress and len(selected)<limit:
            progress=False
            for key in keys:
                while buckets[key]:
                    row=buckets[key].popleft();ends={row['validationReviewUnit'],row['trainReviewUnit']}
                    if not used&ends:
                        selected.append(row);used.update(ends);progress=True;break
                if len(selected)==limit:break
    return selected


def fingerprint(path):
    with Image.open(path) as raw:
        image=ImageOps.exif_transpose(raw).convert('RGB');pixels=hashlib.sha256(image.tobytes()).hexdigest();size=list(image.size)
    return dict(path=path,fileSHA256=sha(path),displaySize=size,displayRGBSHA256=pixels)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--count',type=int,default=10);p.add_argument('--pixel-probe-pairs',type=int,default=40);args=p.parse_args()
    if not 1<=args.count<=20 or not args.count<=args.pixel_probe_pairs<=100:p.error('count 1..20, count <= pixel-probe-pairs <= 100')
    pointer=load(ROOT/'ai_api/verification/latest_data_proposal.json');ready_dir=Path(load(ROOT/'outputs/door_data_readiness/latest.json')['output']);source=ready_dir/'remaining_cross_role_candidates.json';meta=ROOT/pointer['groupDirectory']/'grouped_manifest.csv';group_path=ROOT/pointer['groupDirectory']/'groups.json';roles_path=ROOT/pointer['splitDirectory']/'candidate_roles.csv';constraints_path=ROOT/pointer['suspectedPartConstraintFile'];template=ROOT/'ai_api/similarity_priority_template.html'
    sources=[source,ready_dir/'summary.json',meta,group_path,roles_path,constraints_path,ROOT/'ai_api/verification/latest_data_proposal.json',Path(__file__).resolve(),template]
    hashes={str(p):sha(p) for p in sources}
    for path,expected in load(ready_dir/'summary.json')['sourceHashes'].items():
        if sha(path)!=expected:raise ValueError('Readiness source changed: '+path)
    metadata={r['image_path']:r for r in read_csv(meta)};groups=load(group_path);membership={path:g['groupId'] for g in groups for path in g['members']};role_rows=read_csv(roles_path);by_group={r['group_id']:r for r in role_rows};units={g['groupId']:g['groupId'] for g in groups}
    for c in load(constraints_path):
        for gid in c['duplicateGroupIds']:
            if gid not in units:raise ValueError('Unknown review unit')
            units[gid]=c['constraintId']
    raw=load(source);remaining=[];postponed=[]
    for row in raw:
        a,b=row['validation_image'],row['train_image']
        if a not in metadata or b not in metadata:raise ValueError('Candidate outside train/internal whitelist')
        ga,gb=membership[a],membership[b]
        if ga not in by_group or gb not in by_group:raise ValueError('Held group appeared in cross-role source')
        ra,rb=by_group[ga],by_group[gb]
        if ra['future_split']==rb['future_split'] or ga==gb or units[ga]==units[gb]:raise ValueError('Cross-role source is stale')
        enriched=dict(row,validationReviewUnit=units[ga],trainReviewUnit=units[gb],validationProposedClass=int(ra['proposed_class_id']),trainProposedClass=int(rb['proposed_class_id']),proposedLabelDisagreement=ra['proposed_class_id']!=rb['proposed_class_id'],proposalRoles=[ra['future_split'],rb['future_split']],sourceCategories=[metadata[a]['categories'],metadata[b]['categories']])
        if row.get('previousHumanDecision','UNREVIEWED') not in ('UNREVIEWED','not_reviewed'):
            postponed.append(enriched)
        else:remaining.append(enriched)
    collapsed=distinct_pairs(remaining)
    # Exact decoded-pixel checks on a bounded priority subset, not the whole dataset.
    probe=sorted(collapsed,key=priority)[:args.pixel_probe_pairs];probe_paths=sorted({r[key] for r in probe for key in ['validation_image','train_image']})
    out=ROOT/'outputs/door_similarity_priority'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    print('[PRIORITY OUTPUT]',out,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:fingerprints={r['path']:r for r in pool.map(fingerprint,probe_paths)}
    historical_hash_path=ROOT/'ai_api/verification/data_audit_20261016T181906_711013Z/image_hashes.csv';oldhash={r['image_path']:r['sha256'] for r in read_csv(historical_hash_path)};hashes[str(historical_hash_path)]=sha(historical_hash_path)
    if any(fingerprints[path]['fileSHA256']!=oldhash[path] for path in probe_paths):raise ValueError('Candidate image changed since original audit')
    exact=[]
    for row in probe:
        a,b=(fingerprints[row[key]] for key in ['validation_image','train_image'])
        if a['displaySize']==b['displaySize'] and a['displayRGBSHA256']==b['displayRGBSHA256']:exact.append(dict(row,pixelEvidence=[a,b],status='exact_display_pixel_evidence_requires_group_update_not_user_judgment'))
    exact_keys={(r['validation_image'],r['train_image']) for r in exact}
    scheduling=[r for r in collapsed if (r['validation_image'],r['train_image']) not in exact_keys];chosen=select_diverse(scheduling,args.count)
    for i,row in enumerate(chosen):
        row['caseId']=f'candidate_{i+1:02d}';row['priorityReason']='차기 역할 교차 + 현재 라벨 제안 불일치' if row['proposedLabelDisagreement'] else '차기 역할 교차 + 미확인 관계'
    # Every selected source image must still match the original audit, even if not in the probe set.
    for path in sorted({r[key] for r in chosen for key in ['validation_image','train_image']}):
        if sha(path)!=oldhash[path]:raise ValueError('Selected image changed')
    dump(out/'all_cross_role_source.json',raw);dump(out/'eligible_unresolved_pairs.json',remaining);dump(out/'postponed_previous_inconclusive.json',postponed);dump(out/'best_per_review_unit_pair.json',collapsed);dump(out/'exact_pixel_evidence.json',exact);dump(out/'pixel_fingerprints.json',list(fingerprints.values()));dump(out/'review_queue.json',chosen)
    parts=[];contact=Image.new('RGB',(1000,220*len(chosen)),(245,245,245));draw=ImageDraw.Draw(contact)
    names={0:'GOOD',1:'DEFECT'}
    for i,row in enumerate(chosen):
        parts.append('<article><h2>이번 차수 '+str(i+1)+'번</h2><p>'+html.escape(row['priorityReason'])+'</p><p>왼쪽/오른쪽 라벨 제안: '+names[row['validationProposedClass']]+' / '+names[row['trainProposedClass']]+' · 미래 역할: '+html.escape(' / '.join(row['proposalRoles']))+'</p><div class="pair">')
        draw.text((8,220*i+3),str(i+1)+' '+names[row['validationProposedClass']]+' / '+names[row['trainProposedClass']],fill='black')
        for j,key in enumerate(['validation_image','train_image']):
            name=f'pair_{i+1:02d}_{j}.jpg'
            with Image.open(row[key]) as rawimage:
                preview=ImageOps.exif_transpose(rawimage).convert('RGB');preview.thumbnail((760,560));preview.save(out/name,quality=92);preview.thumbnail((490,185));contact.paste(preview,(j*500,220*i+25))
            parts.append('<a target="_blank" href="'+html.escape(Path(row[key]).as_uri())+'"><img src="'+name+'" alt="'+('기존 내부 검증' if j==0 else '기존 학습')+'"><p>'+('기존 내부 검증' if j==0 else '기존 학습')+'</p></a>')
        parts.append('</div><label>판단 <select id="decision_'+str(i)+'"><option value="UNREVIEWED">미검토</option><option value="SAME_PHOTO">같은 사진</option><option value="POSSIBLY_SAME_PART">같은 실물·다른 촬영 의심</option><option value="DIFFERENT">다른 사진·동일 실물 근거 없음</option><option value="UNSURE">판단 보류</option></select></label><textarea id="reason_'+str(i)+'" placeholder="같은 흠집·경계·반사 패턴 또는 다른 특징 등 근거를 짧게 적어주세요"></textarea></article>')
    contact.save(out/'contact_sheet.jpg',quality=91)
    page=template.read_text().replace('__CARDS__','\n'.join(parts)).replace('__COUNT__',str(len(chosen))).replace('__QUEUE_JSON__',json.dumps(chosen,ensure_ascii=True).replace('<','\\u003c')).replace('__QUEUE_SHA_JSON__',json.dumps(sha(out/'review_queue.json')))
    (out/'index.html').write_text(page)
    summary=dict(status='review_queue_prepared_not_duplicates_resolved',sourceHashes=hashes,sourceCrossRolePairs=len(raw),postponedPreviouslyInconclusivePairs=len(postponed),eligiblePairs=len(remaining),distinctSchedulingUnitPairs=len(collapsed),selectedPairs=len(chosen),selectedLabelDisagreementPairs=sum(r['proposedLabelDisagreement'] for r in chosen),selectedReviewUnits=len({r[k] for r in chosen for k in ['validationReviewUnit','trainReviewUnit']}),pixelProbePairs=len(probe),pixelProbeImages=len(probe_paths),exactDisplayPixelPairs=len(exact),originalImageHashesUnchanged=True,sourceHashesUnchanged=all(sha(p)==h for p,h in hashes.items()),confirmedGroupsModified=False,originalLabelsModified=False,splitApplied=False,trainingStarted=False,finalTestRead=False,readyForTraining=False)
    dump(out/'summary.json',summary)
    report=f'''# 유사 후보 우선순위 정리\n\n최신 라벨 제안과9개 보수적 관계 제약을 반영한 역할 초안을 사용했다. 이미 원본 생성 단계에서 확인된 관계·같은 역할·보류 그룹을 구분한 전체 교차 후보 {len(raw):,}쌍을 보존했다. 이전에 판단 불확실했던 {len(postponed)}쌍은 다시 같은 질문을 반복하지 않고 별도 보류 기록으로 남겼다. 남은 {len(remaining):,}쌍을 기존 중복 그룹 및 실물 의심 제약의 쌍 단위로 정리하면 {len(collapsed):,}개의 검토 일정 후보가 된다. 데이터 삭제나 실물 동일성 확정이 아니다.\n\n우선 {len(probe)}쌍·원본 {len(probe_paths)}장을 실제 디코딩해 EXIF 표시 크기·RGB 픽셀 해시가 완전히 같은지 확인했다. 완전 일치 {len(exact)}쌍. 이 제한된 범위 밖의 픽셀 중복이나 재인코딩·크롭·각도 변화는 보장하지 않는다. 완전 일치가 없다고 다른 실물이라 판단하지 않는다.\n\n검토용으로 {len(chosen)}쌍을 골랐다. 선택한 양쪽 검토 단위는 서로 겹치지 않으며 라벨 제안이 다른 사례를 우선했다. 그 안에서 미래 역할/원본 범주 조합을 번갈아 골라 같은 추천이 몰리지 않게 했다. 유사도 점수는 순서만 정하고 동일/비동일 임계값으로 쓰지 않았다. 이전 수동 판단에서 같은 사진과 다른 사진의 점수 범위가 겹친다는 한계를 유지한다.\n\nindex.html에서 각쌍을 같은 사진 / 같은 실물 의심 / 다른 사진 / 보류로 선택하고 근거를 적어 내보낸다. 배경·차종·구도가 같다는 것만으로 동일 실물을 확정하지 않는다. 다른 사진이라고 선택해도 모든 자료와의 실물 독립성이 확정되지는 않는다. 짧은 근거와 검토자 입력을 필수로 확인한다. 이10쌍을 완료해도 전체 중복 점검 완료라고 하지 않는다. 추가 차수는 이번 결과를 보고 필요 범위를 결정한다.\n\n원본·라벨·분할·모델을 변경하지 않았고 GPU·새 학습·최종 시험은 사용하지 않았다. 재현성 관리로 전체 보류 관계·정렬 규칙·원본 해시·제한된 픽셀 비교·검토 대기열을 새 버전으로 보존했다.\n'''
    (out/'REPORT.md').write_text(report);dump(ROOT/'outputs/door_similarity_priority/latest.json',dict(output=str(out),report=str(out/'REPORT.md'),reviewPage=str(out/'index.html'),queue=str(out/'review_queue.json'),readyForTraining=False));print(json.dumps(dict(output=str(out),**{k:v for k,v in summary.items() if k!='sourceHashes'}),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
