"""Search framing candidates with multiple exemplars and balanced random controls."""
import csv
import hashlib
import html
import json
import random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from ai_api.rank_similarity import features, metrics
from ai_api.duplicate_groups import read_csv, dump

ROOT=Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS=120_000_000


def main():
    latest=json.loads((ROOT/'ai_api/verification/latest_data_proposal.json').read_text())
    manifest=ROOT/latest['representativeDirectory']/'candidate_manifest.csv'
    fingerprint_source=ROOT/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json'
    capture_source=ROOT/'ai_api/verification/capture_selection_20261017T172736_078787Z/selection_proposals.json'
    accepted_source=ROOT/'ai_api/verification/scope_reference_20261017T174241_378142Z/current_reference_status.json'
    audit_source=ROOT/'ai_api/verification/capture_audit_20261017T172917_949346Z/source.json'
    rows=read_csv(manifest);fingerprints={r['image_path']:r for r in json.loads(fingerprint_source.read_text())}
    metadata={r['image_path']:r for r in read_csv(ROOT/latest['groupDirectory']/'grouped_manifest.csv')}
    refs=[dict(id='prior_'+r['id'],path=r['imagePath'],status='prior_capture_candidate_not_boundary_certified') for r in json.loads(capture_source.read_text()) if r['selectionProposal']=='PRIMARY_CAPTURE_CANDIDATE']
    refs.extend(dict(id=r['id'],path=r['imagePath'],status='user_accepted_framing_example') for r in json.loads(accepted_source.read_text())['references'])
    excluded={c['imagePath'] for c in json.loads(audit_source.read_text())['cases']}
    excluded.update(r['imagePath'] for r in json.loads(capture_source.read_text()))
    for r in refs:
        with Image.open(r['path']) as im:r['feature']=features(ImageOps.exif_transpose(im))
        r['dhash']=fingerprints[r['path']]['dhash']
    output=ROOT/'ai_api/verification'/('capture_search_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    print('[CAPTURE SEARCH]',output,flush=True)
    strata=defaultdict(list);coarse=[]
    for r in rows:
        if r['image_path'] in excluded:continue
        distance=min((fingerprints[r['image_path']]['dhash']^ref['dhash']).bit_count() for ref in refs)
        row=dict(r,source_category=metadata[r['image_path']]['categories'],coarse_distance=distance)
        strata[(r['proposed_class_id'],row['source_category'])].append(row)
        coarse.append(dict(image_path=r['image_path'],group_id=r['group_id'],coarse_distance=distance))
    dump(output/'coarse_search.json',coarse)
    shortlist=[r for key,items in sorted(strata.items()) for r in sorted(items,key=lambda r:(r['coarse_distance'],r['image_path']))[:128]]
    def rank(row):
        try:
            with Image.open(row['image_path']) as im:feature=features(ImageOps.exif_transpose(im))
            comparisons=[dict(reference=ref['id'],**metrics(feature,ref['feature'])) for ref in refs]
            best=min(comparisons,key=lambda r:r['rankScore'])
            return dict(row,best_reference=best['reference'],search_score=best['rankScore'],comparisons=comparisons)
        except Exception as exc:return dict(row,error=repr(exc))
    ranked=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,r in enumerate(pool.map(rank,shortlist),1):
            ranked.append(r)
            if i%128==0:print('[RERANK]',i,'/',len(shortlist),flush=True)
    dump(output/'reranked_candidates.json',ranked)
    if any('error' in r for r in ranked):raise ValueError('Candidate image read failed; see reranked_candidates.json')
    selected=[]
    for key in sorted(strata):
        candidates=sorted([r for r in ranked if (r['proposed_class_id'],r['source_category'])==key],key=lambda r:(r['search_score'],r['image_path']))
        picked=[];counts=Counter()
        for r in candidates:
            if counts[r['best_reference']]>=2:continue
            picked.append(r);counts[r['best_reference']]+=1
            if len(picked)==8:break
        for r in candidates:
            if len(picked)==8:break
            if r not in picked:picked.append(r)
        selected.extend(dict(r,selectionArm='retrieval_candidate') for r in picked)
    rng=random.Random(20261018);used={r['image_path'] for r in selected}
    for key,items in sorted(strata.items()):
        controls=rng.sample(sorted([r for r in items if r['image_path'] not in used],key=lambda r:r['image_path']),4)
        selected.extend(dict(r,selectionArm='balanced_random_comparison') for r in controls)
    rng.shuffle(selected)
    assert len(selected)==48 and len({r['group_id'] for r in selected})==48
    records=[];sheets=[Image.new('RGB',(1600,1360),'white') for _ in range(3)]
    for i,row in enumerate(selected):
        ident=f'candidate_{i+1:02d}'
        with Image.open(row['image_path']) as im:image=ImageOps.exif_transpose(im).convert('RGB')
        image.thumbnail((1200,1000));image.save(output/(ident+'.jpg'),quality=94)
        thumb=image.copy();thumb.thumbnail((390,305));x=i%4*400;y=(i%16)//4*340
        sheets[i//16].paste(thumb,(x,y+28));ImageDraw.Draw(sheets[i//16]).text((x+6,y+6),ident,fill='black')
        records.append(dict(id=ident,**row,image_sha256=hashlib.sha256(Path(row['image_path']).read_bytes()).hexdigest()))
    for i,sheet in enumerate(sheets):sheet.save(output/f'contact_{i+1}.jpg',quality=93)
    dump(output/'selected_cases.json',records)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>도어 구도 후보'+'</title><h1>도어 구도 후보48장</h1><p>검색32장과 유형별 무작위 비교16장을 섞었습니다. 양품/불량·검색순위는 표시하지 않습니다. 사진을 누르면 원본을 엽니다. 원본 라벨의 정답이나 촬영 적합성을 확정하지 않았습니다.</p>']
    for r in records:parts.append('<h2>'+r['id']+'</h2><a href="'+html.escape(Path(r['image_path']).as_uri(),quote=True)+'"><img style="width:95%;max-width:1200px" src="'+r['id']+'.jpg"></a>')
    (output/'index.html').write_text('\n'.join(parts))
    sources=[manifest,fingerprint_source,capture_source,accepted_source,audit_source]
    dump(output/'summary.json',dict(status='search_complete_visual_review_pending',population=len(rows),searchedUnreviewed=len(coarse),shortlist=len(shortlist),retrieved=32,randomComparison=16,
          sourceHashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},references=[{k:v for k,v in r.items() if k!='feature'} for r in refs],
          method='Full cached dHash search; top128 per class/category reranked by RGB/edge/aspect against8 exemplars; reference diversity capped where possible; balanced random controls',
          limitations='Retrieval may favor reference colors/scenes and miss suitable frames; no semantic full-door detector, no population suitability estimate',
          originalsModified=False,finalTestUsed=False,modelRun=False,labelsChanged=False,splitChanged=False))
    print('[CAPTURE SEARCH READY]',output/'index.html',flush=True)


if __name__=='__main__':main()
