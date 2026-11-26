"""Target scratch-defect framing candidates with diverse retrieval and random comparisons."""
import csv,hashlib,html,json,random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
from ai_api.rank_similarity import features,metrics
from ai_api.duplicate_groups import read_csv,dump
ROOT=Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS=120_000_000

def diverse(rows, fingerprints, count, used=()):
    pool={r['image_path']:r for r in sorted(rows,key=lambda r:r['image_path']) if r['image_path'] not in used}
    result=[];anchors=[fingerprints[p]['dhash'] for p in used if p in fingerprints]
    while pool and len(result)<count:
        if anchors:
            path=max(pool,key=lambda p:(min((fingerprints[p]['dhash']^h).bit_count() for h in anchors),p))
        else:path=next(iter(pool))
        result.append(pool.pop(path));anchors.append(fingerprints[path]['dhash'])
    return result

def main():
    latest=json.loads((ROOT/'ai_api/verification/latest_data_proposal.json').read_text())
    manifest=ROOT/latest['representativeDirectory']/'candidate_manifest.csv'
    fp_source=ROOT/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json'
    accepted=ROOT/'ai_api/verification/capture_search_20261017T175242_632360Z/user_revised_selection.json'
    earlier=ROOT/'ai_api/verification/scope_reference_20261017T174241_378142Z/current_reference_status.json'
    rows=read_csv(manifest);fps={r['image_path']:r for r in json.loads(fp_source.read_text())}
    metadata={r['image_path']:r for r in read_csv(ROOT/latest['groupDirectory']/'grouped_manifest.csv')}
    for r in rows:r['source_category']=metadata[r['image_path']]['categories']
    refs=[dict(path=r['image_path'],id=r['id']) for r in json.loads(accepted.read_text()) if r.get('acceptedByUser')]
    refs.extend(dict(path=r['imagePath'],id=r['id']) for r in json.loads(earlier.read_text())['references'])
    exclusions=set()
    sources=[manifest,fp_source,accepted,earlier]
    for folder,key,file in [('capture_audit_20261017T172917_949346Z','imagePath','source.json'),('capture_selection_20261017T172736_078787Z','imagePath','selection_proposals.json'),('capture_search_20261017T175242_632360Z','image_path','selected_cases.json')]:
        p=ROOT/'ai_api/verification'/folder/file;sources.append(p);d=json.loads(p.read_text());items=d['cases'] if isinstance(d,dict) else d;exclusions.update(r[key] for r in items)
    available=[r for r in rows if r['image_path'] not in exclusions]
    scratch=[r for r in available if r['proposed_class_id']=='1' and r['source_category']=='스크래치']
    output=ROOT/'ai_api/verification'/('scratch_scope_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir();print('[SCRATCH SEARCH]',output,flush=True)
    for r in refs:
        with Image.open(r['path']) as im:r['feature']=features(ImageOps.exif_transpose(im))
    coarse=sorted(scratch,key=lambda r:(min((fps[r['image_path']]['dhash']^fps[ref['path']]['dhash']).bit_count() for ref in refs),r['image_path']))
    def score(row):
        with Image.open(row['image_path']) as im:feature=features(ImageOps.exif_transpose(im))
        scores=[dict(reference=ref['id'],**metrics(feature,ref['feature'])) for ref in refs]
        # Do not use RGB color to prioritize white/silver cars.
        best=min(scores,key=lambda s:s['relativeEdgeDifference']+s['aspectDifference'])
        return dict(row,retrievalScore=best['relativeEdgeDifference']+best['aspectDifference'],bestReference=best['reference'])
    ranked=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,r in enumerate(pool.map(score,coarse[:768]),1):
            ranked.append(r)
            if i%192==0:print('[SCRATCH RERANK]',i,'/768',flush=True)
    ranked.sort(key=lambda r:(r['retrievalScore'],r['image_path']));dump(output/'ranked_shortlist.json',ranked)
    selected=[];chosen=[]
    for r in ranked:
        h=fps[r['image_path']]['dhash']
        if chosen and min((h^fps[x['image_path']]['dhash']).bit_count() for x in chosen)<6:continue
        chosen.append(r)
        if len(chosen)==32:break
    if len(chosen)<32:raise ValueError('Insufficient diverse retrieval candidates')
    selected.extend(dict(r,selectionArm='scratch_structural_retrieval') for r in chosen)
    far=diverse(scratch,fps,16,{r['image_path'] for r in selected});selected.extend(dict(r,selectionArm='scratch_hash_diversity') for r in far)
    rng=random.Random(20261019);used={r['image_path'] for r in selected}
    controls=rng.sample(sorted([r for r in scratch if r['image_path'] not in used],key=lambda r:r['image_path']),16)
    selected.extend(dict(r,selectionArm='scratch_random_comparison') for r in controls)
    other=[r for r in available if not(r['proposed_class_id']=='1' and r['source_category']=='스크래치')]
    # Additional source strata: GOOD scratch8, GOOD exterior4, DEFECT exterior4.
    for quality,category,count in [('0','스크래치',8),('0','외관 손상',4),('1','외관 손상',4)]:
        pool=[r for r in other if r['proposed_class_id']==quality and r['source_category']==category]
        selected.extend(dict(r,selectionArm='other_stratum_diversity') for r in diverse(pool,fps,count))
    rng.shuffle(selected);assert len(selected)==80 and len({r['group_id'] for r in selected})==80
    records=[];sheets=[Image.new('RGB',(1600,1360),'white') for _ in range(5)]
    for i,row in enumerate(selected):
        ident=f'scratch_candidate_{i+1:02d}'
        with Image.open(row['image_path']) as im:image=ImageOps.exif_transpose(im).convert('RGB')
        image.thumbnail((1400,1000));image.save(output/(ident+'.jpg'),quality=94)
        thumb=image.copy();thumb.thumbnail((390,305));x=i%4*400;y=(i%16)//4*340;sheets[i//16].paste(thumb,(x,y+28));ImageDraw.Draw(sheets[i//16]).text((x+6,y+6),ident,fill='black')
        records.append(dict(id=ident,**row,image_sha256=hashlib.sha256(Path(row['image_path']).read_bytes()).hexdigest()))
    for i,sheet in enumerate(sheets):sheet.save(output/f'contact_{i+1}.jpg',quality=93)
    dump(output/'selected_cases.json',records)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>스크래치 구도 보완</title><h1>스크래치 구도 보완80장</h1><p>스크래치 불량64장과 다른 유형16장을 섞었습니다. 선정 팔과 라벨은 사진 관찰 화면에서 숨겼습니다. 전수 적합성 검사나 성능 평가는 아닙니다.</p>']
    for r in records:parts.append('<h2>'+r['id']+'</h2><a href="'+html.escape(Path(r['image_path']).as_uri(),quote=True)+'"><img style="width:95%;max-width:1400px" src="'+r['id']+'.jpg"></a>')
    (output/'index.html').write_text('\n'.join(parts))
    dump(output/'summary.json',dict(status='prepared_for_visual_review',population=len(rows),availableScratchDefects=len(scratch),shortlist=len(ranked),selected=80,arms=dict(Counter(r['selectionArm'] for r in records)),seed=20261019,
         sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},references=[dict(id=r['id'],path=r['path']) for r in refs],
         method='Cached dHash coarse search; edge/aspect rerank without RGB score; hash diversity and random comparisons. Diversity is not physical-car identity.',
         scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),labelsChanged=False,splitChanged=False,modelRun=False,finalTestUsed=False))
    print('[SCRATCH READY]',output/'index.html',flush=True)

if __name__=='__main__':main()
