"""Prepare visibility/region annotations from existing eight images; no model execution."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageOps
from frame_model.check import ROOT,read_image
from frame_model.train import dump


def main():
    probe_path=Path(json.loads((ROOT/'frame_model/latest_cam_probe.json').read_text())['plan']);probe=json.loads(probe_path.read_text())
    out=ROOT/'outputs/frame_input_background'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    cases=[]
    for item in probe['items']:
        ident=item['id'];display,base=read_image(item['source'])
        if hashlib.sha256(Path(item['display_path']).read_bytes()).hexdigest()!=item['display_sha256']:raise ValueError('Display reference changed')
        with Image.open(item['display_path']) as existing:
            if existing.size!=display.size or existing.convert('RGB').tobytes()!=display.tobytes():raise ValueError('Original display pixels differ')
        preview=display.copy();preview.thumbnail((1200,1200));preview.save(out/f'{ident}.jpg',quality=92)
        base.save(out/f'{ident}_224.png');base.resize((448,448),Image.Resampling.NEAREST).save(out/f'{ident}_224_enlarged.png')
        ImageOps.pad(display,(448,448),method=Image.Resampling.BICUBIC,color=(124,116,104)).save(out/f'{ident}_448.png')
        cases.append({'id':ident,'type':item['pair']['defect_type'],'sourceQuality':'DEFECT' if int(item['pair']['actual']) else 'GOOD (두 모델 오탐)','source':item['source'],'displaySize':item['display_size'],'originalUrl':item['display_path'],'preview':f'{ident}.jpg','input224':f'{ident}_224.png','input224Enlarged':f'{ident}_224_enlarged.png','input448':f'{ident}_448.png','asset_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in [f'{ident}.jpg',f'{ident}_224.png',f'{ident}_224_enlarged.png',f'{ident}_448.png']}})
    source={'schema':'frame-input-background-regions-v1','reviewId':out.name,'probePlan':str(probe_path),'probePlanSha256':hashlib.sha256(probe_path.read_bytes()).hexdigest(),'coordinateSystem':'normalized EXIF-corrected display coordinates, not padded input','cases':cases,'purpose':'Visual information comparison and human region semantics; 448 is not inference or a performance measurement','trainingPerformed':False,'serviceChanged':False}
    dump(out/'source.json',source)
    template=(ROOT/'frame_model/input_background.html').read_text();(out/'index.html').write_text(template.replace('__DATA__',json.dumps(source,ensure_ascii=False).replace('<','\\u003c')))
    dump(ROOT/'frame_model/latest_input_background.json',{'directory':str(out),'html':str(out/'index.html'),'source':str(out/'source.json')})
    print('[INPUT/BACKGROUND REVIEW]',out/'index.html')

if __name__=='__main__':main()
