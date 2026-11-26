"""Verify completed candidate audit and summarize without confirming duplicates or changing data."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from frame_model.check import ROOT
from frame_model.experiments import load_plan
from frame_model.train import dump


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--audit',type=Path,required=True);args=parser.parse_args();out=args.audit
    summary=json.loads((out/'summary.json').read_text())
    if not summary['status'].startswith('complete'):raise ValueError('Audit not complete')
    path=Path(summary['plan'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=summary['plan_sha256']:raise ValueError('Plan changed')
    _,_,experiments=load_plan(path);source={r['image_id']:r for rows in experiments['unified'][1].values() for r in rows}
    records=[json.loads(line) for line in (out/'fingerprints.jsonl').read_text().splitlines()]
    if len(records)!=len(source) or {r['image_id'] for r in records}!=set(source):raise ValueError('Fingerprint coverage differs')
    by_role=Counter(r.get('role','decode_error') for r in records);type_hits={};all_hits=set();by_type=Counter();cross=0;exact=0;total=0;closest={}
    with (out/'similarity_candidates.jsonl').open() as stream:
        for line in stream:
            pair=json.loads(line);a=source[pair['validation_image']];b=source[pair['train_image']]
            if a['split']!='model_selection' or b['split']!='train':raise ValueError('Candidate role mismatch')
            total+=1;all_hits.add(a['image_id']);by_type[a['defect_type']]+=1;type_hits.setdefault(a['defect_type'],set()).add(a['image_id']);cross+=not pair['same_source_quality'];exact+=pair['exact_display_pixels']
            key=(not pair['exact_display_pixels'],pair['rankScore'])
            if a['image_id'] not in closest or key<closest[a['image_id']][0]:closest[a['image_id']]=(key,pair)
    if (total,len(all_hits),cross,exact)!=(summary['candidate_pairs'],summary['validation_images_with_candidates'],summary['cross_source_quality_pairs'],summary['exact_display_pixel_pairs']):raise ValueError('Candidate counts differ')
    gallery=json.loads((out/'gallery_candidates.json').read_text())
    for pair in gallery:
        for key in ['validation_image','train_image']:
            if not (out/'gallery'/f'{pair[key]}.jpg').is_file():raise ValueError('Gallery asset missing')
    report={'status':'verified_candidates_unreviewed','images':len(records),'roles':dict(by_role),'pairs':total,'validation_images_with_candidates':len(all_hits),'cross_source_quality_pairs':cross,'exact_display_pixel_pairs':exact,'candidate_pairs_by_validation_type':dict(by_type),'validation_hits_by_type':{k:len(v) for k,v in type_hits.items()},'gallery_pairs':len(gallery),'human_verified_duplicates':None,'split_changed':False,'metrics_recomputed':False,'file_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['summary.json','fingerprints.jsonl','similarity_candidates.jsonl','gallery_candidates.json']}}
    dump(out/'verified_summary.json',report)
    lines=['# 프레임 학습·내부 검증 유사 사진 점검 결과','',f"실제 점검 대상 {len(records):,}장. 학습 {by_role['train']:,}장/내부 검증 {by_role['model_selection']:,}장. 읽기 오류 {len(summary['decode_errors'])}건.",'',f'거리조건 유사 후보 {total:,}쌍, 해당 후보가 있는 내부 검증 사진 {len(all_hits):,}장.',f'EXIF 보정 표시 픽셀이 정확히 같은 후보 {exact:,}쌍. 품질 라벨이 다른 유사 후보 {cross:,}쌍.','', '| 검증 유형 | 유사 후보쌍 | 후보가 있는 검증 사진 |','|---|---:|---:|']
    for kind in sorted({r['defect_type'] for r in source.values() if r['split']=='model_selection'}):lines.append(f'| {kind} | {by_type[kind]:,} | {len(type_hits.get(kind,set())):,} |')
    lines+=['',f'원본 축소 비교 화면은 index.html의 최대50쌍 중 실제 {len(gallery)}쌍입니다. 전체 후보는 similarity_candidates.jsonl에 있습니다.','', '## 해석','', '위 수량은 자동 유사 후보이며 중복 확정이나 누수율이 아닙니다. 반복 공정 배경·고정 카메라·평탄한 표면도 후보로 잡힐 수 있습니다. 반대로 다른각도·crop·회전·조명변화·동일실물 반복은 놓칠 수 있습니다. 픽셀동일0건이어도 실물중복이없다는뜻은아닙니다.','', '품질 라벨이 다른 후보도 작은 손상 차이가 실제로 있을 수 있어 자동 라벨 오류로 판단하지 않습니다. 같은사진/재인코딩, 동일실물추정, 다른실물반복장면, 판단불가를 원본으로 구분해야 합니다. 현재내부검증점수의높은이유도이점검만으로확정할수없습니다.','', '모델·전처리·원본·라벨·분할·SQLite는 변경하지 않았습니다. 독립최종시험·보정·정책자료는 읽지 않았고 재학습/점수수정도 하지 않았습니다.','', '다음은 상위 후보의 원본 비교로 실제 관계를 판단하고, 확인된 연결만 별도 그룹 제안으로 기록하는 것입니다. 전체후보를그대로그룹으로합치지않습니다.']
    (out/'RESULT.md').write_text('\n'.join(lines)+'\n');print('[SIMILARITY VERIFIED]',out/'RESULT.md');print(json.dumps({k:v for k,v in report.items() if k!='file_sha256'},ensure_ascii=False))

if __name__=='__main__':main()
