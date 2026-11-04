"""Empirical development metrics for explicit thresholds; never ready/activate a policy."""
import argparse
import csv
import json
import math
from pathlib import Path


def evaluate(rows,threshold):
    if not math.isfinite(threshold) or not 0<=threshold<=1:raise ValueError('Threshold must be finite in [0,1]')
    total=len(rows)
    if not total:raise ValueError('Empty score table')
    defects=auto=bad_auto=good_auto=0
    for row in rows:
        y=int(row['class_id']);raw=float(row['raw_defect_score']);pred=int(row['predicted_class'])
        if y not in (0,1) or pred not in (0,1) or not math.isfinite(raw) or not 0<=raw<=1 or pred!=int(raw>=.5):raise ValueError('Invalid raw label/score/class')
        c=row.get('calibrated_defect_probability')
        c=None if c is None or c=='' else float(c)
        if c is not None and (not math.isfinite(c) or not 0<=c<=1):raise ValueError('Invalid calibrated probability')
        # Production GOOD gate is mandatory even if DEFECT has a low calibrated value.
        passed=pred==0 and c is not None and c<=threshold
        defects+=y
        auto+=passed
        bad_auto+=passed and y==1
        good_auto+=passed and y==0
    return dict(sampleCount=total,actualDefectCount=defects,autoPassCount=auto,reviewCount=total-auto,
                missedDefectCount=bad_auto,goodAutoPassCount=good_auto,
                automationRate=auto/total,reviewRate=(total-auto)/total,
                missedDefectRate=bad_auto/defects if defects else None,
                autoPassContaminationRate=bad_auto/auto if auto else None,
                defectReviewCaptureRate=1-bad_auto/defects if defects else None)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scores',type=Path,required=True);p.add_argument('--thresholds',required=True);p.add_argument('--model-version',required=True);p.add_argument('--calibrator-version',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.scores.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    points=[dict(passThreshold=float(t),metrics=evaluate(rows,float(t))) for t in a.thresholds.split(',')]
    report=dict(schema='policy-development-metrics-only-v1',modelVersion=a.model_version,calibratorVersion=a.calibrator_version,
                points=points,releaseReady=False,validatedRange=None,productionModified=False,
                note='Empirical development sweep; not a confidence guarantee or independent policy test. Not an admin registration payload.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print('Development metrics written. No policy registered or activated.')


if __name__=='__main__':main()
