"""Read-only DOOR known-link audit; saved-score subsets are not new evaluations."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from ai_api.duplicate_groups import ROOT, read_csv


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def metrics(rows):
    counts=Counter(('TP' if int(r['predicted_class']) else 'FN') if int(r['class_id']) else ('FP' if int(r['predicted_class']) else 'TN') for r in rows)
    tp,tn,fp,fn=(counts[k] for k in ('TP','TN','FP','FN'))
    return dict(n=len(rows),tp=tp,tn=tn,fp=fp,fn=fn,accuracy=(tp+tn)/len(rows) if rows else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--groups',type=Path,required=True)
    args=parser.parse_args(); directory=args.groups.resolve()
    summary=json.loads((directory/'summary.json').read_text())
    for p,digest in summary['sourceHashes'].items():
        if sha(p)!=digest:raise ValueError('Source changed: '+p)
    groups=json.loads((directory/'groups.json').read_text())
    edges=json.loads((directory/'evidence_edges.json').read_text())
    train=read_csv(ROOT/'outputs/manifests/door_train.csv'); valid=read_csv(ROOT/'outputs/manifests/door_internal_validation.csv')
    assert (len(train),len(valid))==(11554,2039)
    by_path={r['image_path']:r for r in train+valid}; train_paths={r['image_path'] for r in train}; valid_paths={r['image_path'] for r in valid}
    assert len(by_path)==13593
    predpath=ROOT/'outputs/training/door_swin_tiny_20261008_183758_369671/best_internal_validation_predictions.csv'
    preds=read_csv(predpath);assert len(preds)==2039 and {r['image_path'] for r in preds}==valid_paths
    for r in preds:
        assert int(r['class_id'])==int(by_path[r['image_path']]['class_id'])
        assert int(r['predicted_class'])==int(float(r['raw_defect_score'])>=.5)
    hashrows=read_csv(ROOT/'ai_api/verification/data_audit_20261016T181906_711013Z/image_hashes.csv')
    oldhash={r['image_path']:r['sha256'] for r in hashrows}
    linked={p for e in edges for p in (e['a'],e['b'])}
    changed=[p for p in sorted(linked) if sha(p)!=oldhash[p]]
    if changed:raise ValueError('Linked image bytes changed: '+str(len(changed)))
    cross=[g for g in groups if set(g['members'])&train_paths and set(g['members'])&valid_paths]
    affected={p for g in cross for p in g['members'] if p in valid_paths}
    exact_digests={oldhash[p] for p in train_paths}
    exact_valid={p for p in valid_paths if oldhash[p] in exact_digests}
    lookup={p:g for g in cross for p in g['members']}
    output=ROOT/'outputs/door_leakage_audit'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');output.mkdir(parents=True)
    rows=[]
    for r in preds:
        if r['image_path'] in affected:
            g=lookup[r['image_path']]
            rows.append(dict(r,groupId=g['groupId'],groupLabelConflict=g['labelConflict'],exactFileMatchToTrain=r['image_path'] in exact_valid,trainMembers=sum(p in train_paths for p in g['members'])))
    with (output/'affected_internal_predictions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result=dict(groupSource=str(directory),sourceHashes=summary['sourceHashes'],predictionsSHA256=sha(predpath),linkedImagesFreshHashChecked=len(linked),linkedImageChanges=changed,edgeEvidenceCounts=dict(Counter(e['evidence'] for e in edges)),imageCount=13593,knownCrossSplitGroups=len(cross),affectedValidationImages=len(affected),exactFileCrossSplitValidationImages=len(exact_valid),additionalUserConfirmedValidationImages=len(affected-exact_valid),labelConflictGroups=sum(g['labelConflict'] for g in groups),allInternal=metrics(preds),knownCrossSplitSubset=metrics([r for r in preds if r['image_path'] in affected]),remainingExploratorySubset=metrics([r for r in preds if r['image_path'] not in affected]),originalsModified=False,splitApplied=False,finalTestRead=False,gpuInferenceExecuted=False,limitations=['Saved predictions only; no fresh model evaluation','Remaining subset is neither duplicate-free nor independent','No causal estimate of score inflation','Full 13593 current image hashes not recomputed; all evidence-linked images checked','User-confirmed links are human evidence, not proof of physical-part identity'])
    (output/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    a,b,c=(result[k] for k in ('allInternal','knownCrossSplitSubset','remainingExploratorySubset'))
    report='# DOOR 높은 성능 수치 점검 — 기존 중복 근거 재집계\n'
    report+=f'''\n학습 11,554장과 내부 검증 2,039장만 사용했다. 기존 검토·해시 근거를 재사용하고 연결 근거에 등장하는 원본 {len(linked)}장의 현재 SHA256을 다시 확인했다. 변경 0장. 전체 원본의 현재 해시를 다시 계산한 것은 아니다.\n\n- 알려진 분할 교차 그룹: {len(cross)}개\n- 해당 내부 검증 사진: {len(affected)}장 ({len(affected)/2039:.2%})\n- 그중 학습 사진과 파일 해시가 같은 검증 사진: {len(exact_valid)}장\n- 추가 수동 확인 연결로 포함된 검증 사진: {len(affected-exact_valid)}장\n- 전체 그룹 중 원래 클래스가 충돌하는 그룹: {result['labelConflictGroups']}개. 원래 라벨 보존.\n\n| 저장 예측 집계 범위 | 장수 | TP/TN/FP/FN | 정확도 | 불량 F1 |\n|---|---:|---|---:|---:|\n'''
    for label,m in [('기존 내부 검증 전체',a),('알려진 교차 그룹 포함 사진',b),('나머지 사진 — 사후 참고 집계',c)]:
        report+=f"|{label}|{m['n']}|{m['tp']}/{m['tn']}/{m['fp']}/{m['fn']}|{m['accuracy']:.6%}|{m['f1']:.6%}|\n"
    report+='''\n## 판단과 다음 작업\n\n분할을 넘는 중복은 실제 평가의 독립성을 약화시키는 문제다. 그러나 이 집계만으로 높은 점수가 중복 때문에 발생했다고 단정하거나, 몇 % 과대평가됐다고 계산할 수 없다. 제외 전후 점수는 표본 구성과 난이도가 달라 직접적인 인과 비교가 아니다. 나머지 사진도 미확인 유사·같은 실물 관계와 모델 선택 사용 이력이 남는다.\n\n현재 DOOR 모델은 개발 연동 기준으로 보존한다. 기존 성능을 독립 최종 시험 또는 공정 성능으로 발표하지 않는다. 보정·자동 통과 검증 완료로도 표현하지 않는다.\n\n다음은 미확인 후보의 검토 범위와 라벨 충돌의 원본 quality 연결을 확인해 차기 실험 그룹 근거를 고정하는 작업이다. 이미 작성한 라벨 검토와 대표·분할 후보도 재사용하며 원본 라벨을 자동 변경하지 않는다. 별도 실험 승인 후 그룹 단위 분할·새 초기화 학습·독립 평가를 설계한다. 현재 best.pt의 노출 이력은 재분할로 사라지지 않는다. 최종 시험 1,700장은 이번 작업에서 읽지 않았다.\n\n모델 성능·판정 변경 없음. 실행 환경 변경 없음. 재현성 관리: 기존 그룹 도구 재실행, 근거 해시 대조, 연결 이미지 해시 재확인, 저장 예측 재집계 및 새 결과 보존.\n'''
    (output/'REPORT.md').write_text(report)
    print(json.dumps(dict(output=str(output),**result),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
