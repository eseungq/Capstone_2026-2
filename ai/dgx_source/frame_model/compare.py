"""Compare paired predictions from a verified frame experiment suite (CPU only)."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from frame_model.train import metrics,dump,write_csv


def predictions(rows,cutoff=0.5):
    result={}
    for row in rows:
        ident=row['image_id'];actual=int(row['actual']);pred=int(row['predicted']);score=float(row['raw_defect_score'])
        if ident in result:raise ValueError('Duplicate prediction image')
        if actual not in [0,1] or pred not in [0,1] or not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid prediction')
        if pred!=int(score>=cutoff):raise ValueError('Score/class mismatch')
        result[ident]={**row,'actual':actual,'predicted':pred,'raw_defect_score':score}
    return result


def paired(unified,specialist):
    a=predictions(unified);b=predictions(specialist)
    if not a or set(a)!=set(b):raise ValueError('Paired image IDs differ or empty')
    details=[];counts={'both_correct':0,'unified_only_wrong':0,'specialist_only_wrong':0,'both_wrong':0}
    for ident in sorted(a):
        x=a[ident];y=b[ident]
        if (x['actual'],x['defect_type'])!=(y['actual'],y['defect_type']):raise ValueError('Paired labels/types differ')
        xc=x['actual']==x['predicted'];yc=y['actual']==y['predicted']
        category='both_correct' if xc and yc else 'unified_only_wrong' if yc else 'specialist_only_wrong' if xc else 'both_wrong'
        counts[category]+=1
        details.append({'image_id':ident,'defect_type':x['defect_type'],'actual':x['actual'],'unified_prediction':x['predicted'],'specialist_prediction':y['predicted'],'unified_score':x['raw_defect_score'],'specialist_score':y['raw_defect_score'],'category':category})
    return {'unified':metrics(list(a.values())),'specialist':metrics(list(b.values())),'paired_counts':counts},details


def compare_suite(path,require_complete=True):
    suite=json.loads(path.read_text())
    if require_complete and suite['status']!='passed':raise ValueError('Suite not passed')
    if len(suite['runs'])!=5 or any(r['status']!='passed' for r in suite['runs']):raise ValueError('Need all five successful runs')
    plan_path=Path(suite['plan'])
    if hashlib.sha256(plan_path.read_bytes()).hexdigest()!=suite['plan_sha256']:raise ValueError('Plan changed')
    from frame_model.experiments import load_plan
    _,_,experiments=load_plan(plan_path)
    smoke=suite['mode']=='smoke';filename='smoke_predictions_NOT_EVALUATION.csv' if smoke else 'best_model_selection_predictions.csv'
    collected={};fingerprints=set();versions=set();last_collected={}
    expected_ids={'unified','type_01','type_02','type_03','type_04'}
    if {r['experiment_id'] for r in suite['runs']}!=expected_ids:raise ValueError('Suite experiment IDs differ')
    for run in suite['runs']:
        directory=Path(run['directory']);config=json.loads((directory/'run_config.json').read_text())
        status=json.loads((directory/'status.json').read_text())
        if status['status']!='passed' or bool(status['quality_evaluation'])==smoke:raise ValueError('Run status/mode differs')
        context=config['experiment_context']
        if context['plan_sha256']!=suite['plan_sha256'] or context['experiment_id']!=run['experiment_id']:raise ValueError('Run provenance differs')
        if config['mode']!=suite['mode']:raise ValueError('Mixed smoke/training')
        fingerprints.add(config['initial_tensor_sha256']);versions.add(json.dumps(config['versions'],sort_keys=True))
        artifacts=json.loads((directory/'artifacts.json').read_text())
        for name in [filename,'run_config.json','model_selection_used.csv','train_used.csv','last_model_selection_predictions.csv']:
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=artifacts.get(name):raise ValueError('Artifact hash differs: '+name)
        rows=list(csv.DictReader(io.StringIO((directory/filename).read_text())));mapping=predictions(rows)
        used=list(csv.DictReader(io.StringIO((directory/'model_selection_used.csv').read_text())))
        if set(mapping)!={r['image_id'] for r in used}:raise ValueError('Prediction coverage differs')
        for row in used:
            actual=mapping[row['image_id']]
            if actual['actual']!=int(row['class_id']) or actual['defect_type']!=row['defect_type']:raise ValueError('Prediction/manifest labels differ')
        full=experiments[run['experiment_id']][1]
        from frame_model.train import subset
        for role in ['train','model_selection']:
            expected=subset(full[role],16 if role=='train' else 8) if smoke else full[role]
            actual=list(csv.DictReader(io.StringIO((directory/f'{role}_used.csv').read_text())))
            if actual!=expected:raise ValueError('Run did not use frozen experiment subset')
        collected[run['experiment_id']]=rows
        last_collected[run['experiment_id']]=list(csv.DictReader(io.StringIO((directory/'last_model_selection_predictions.csv').read_text())))
    if len(fingerprints)!=1 or len(versions)!=1:raise ValueError('Initialization or environment differs')
    results={};last_results={};details=[]
    for ident,(exp,_) in experiments.items():
        if ident=='unified':continue
        kind=exp['inspection_type']
        results[kind],rows=paired([r for r in collected['unified'] if r['defect_type']==kind],collected[ident]);details.extend(rows)
        last_results[kind],_=paired([r for r in last_collected['unified'] if r['defect_type']==kind],last_collected[ident])
    macro={name:{metric:sum(v[name][metric] for v in results.values())/len(results) if all(v[name][metric] is not None for v in results.values()) else None for metric in ['f1','false_negative_rate','false_positive_rate']} for name in ['unified','specialist']}
    report={'status':'passed','mode':suite['mode'],'quality_evaluation':not smoke,'initial_tensor_sha256':next(iter(fingerprints)),'by_type':results,'macro_type_average':macro,'last_epoch_by_type':last_results,'limitations':['Smoke metrics are execution checks only.' if smoke else 'Model-selection scores are not independent final performance.','No operating quality targets or automatic winner.','No CAM, calibration, policy, bootstrap or deployment validation performed here.']}
    dump(path.parent/'comparison.json',report);write_csv(path.parent/'paired_predictions.csv',details)
    label='실행 확인용 — 성능 평가 아님' if smoke else '모델 선택 자료 비교 — 독립 최종 시험 아님'
    lines=['# 프레임 모델 비교', '',label,'','동일 초기 가중치·환경·사진·라벨·점수 범위·아티팩트 해시를 확인했습니다.','', '| 유형 | 통합 F1 | 개별 F1 | 통합 FN | 개별 FN |','|---|---:|---:|---:|---:|']
    for kind,r in results.items():lines.append(f"| {kind} | {r['unified']['f1']} | {r['specialist']['f1']} | {r['unified']['fn']} | {r['specialist']['fn']} |")
    lines+=['','수치만으로 운영 모델을 자동 선택하지 않습니다. CAM·촬영 조건·성능 목표·독립 평가가 남아 있습니다.']
    (path.parent/'COMPARISON.md').write_text('\n'.join(lines)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--suite',type=Path,required=True);args=parser.parse_args()
    compare_suite(args.suite);print('[COMPARISON REPORT]',args.suite.parent/'COMPARISON.md')

if __name__=='__main__':main()
