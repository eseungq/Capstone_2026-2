"""Audit image orientation/padding/inverse display geometry without loading model weights."""
import argparse,ast,hashlib,html,importlib.metadata,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import torch
from PIL import Image,ImageOps,ImageDraw
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF

ROOT=Path('/path/to/private/validated-project')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def label_preview(image,boxes,filename):
 canvas=image.copy();draw=ImageDraw.Draw(canvas)
 for x,y,w,h in boxes:draw.rectangle((x,y,x+w,y+h),outline=(0,220,70),width=max(3,image.width//500))
 canvas.thumbnail((1400,1000));canvas.save(filename,quality=92)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
 assert not torch.cuda.is_available()
 torch.set_num_threads(2);torch.set_num_interop_threads(1)
 methods=Path(json.loads((ROOT/'ai_api/cam_methods_20261104/latest.json').read_text())['output']);frozen=json.loads((methods/'manifest.json').read_text())
 versions={key:importlib.metadata.version(key) for key in frozen['versions']};assert versions==frozen['versions']
 src=Path(frozen['datasetSource']);assert sha(src)==frozen['datasetSourceSHA256']
 tree=ast.parse(src.read_text());mn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');dn=next(n for n in mn.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
 mean=frozen['normalization']['mean'];std=frozen['normalization']['std'];fill=(124,116,104)
 cfg=json.loads((Path(frozen['modelRuns']['new'])/'run_config.json').read_text())['config']
 ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg,mean=mean,std=std,fill=fill);exec(compile(ast.Module(body=[dn],type_ignores=[]),str(src),'exec'),ns);dataset=ns['DoorDataset']
 report=dict(scope='coordinate pipeline audit, source-label display and coarse-resolution diagnostic',modelWeightsLoaded=False,modelInferencePerformed=False,modelOrThresholdChanged=False,rawCAMModified=False,sourceLabelsUsedAsCertifiedGroundTruth=False,versions=versions,samples=[])
 transpose={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
 sections=[]
 for sample in frozen['samples']:
  sid=sample['id'];folder=out/sid;folder.mkdir();path=Path(sample['image_path']);assert sha(path)==sample['imageSHA256']
  with Image.open(path) as raw:
   orientation=raw.getexif().get(274,1);raw_size=list(raw.size);image=ImageOps.exif_transpose(raw).convert('RGB')
  assert list(image.size)==sample['displaySize']
  expected=ImageOps.pad(image,(224,224),method=Image.Resampling.BICUBIC,color=fill)
  with Image.open(methods/sid/'input224.png') as stored:stored_array=np.asarray(stored.convert('RGB'))
  assert np.array_equal(np.asarray(expected),stored_array),'saved input differs from original EXIF-corrected preprocessing'
  x=dataset([dict(image_path=str(path),class_id=1)])[0][0]
  recovered=((x*torch.tensor(std)[:,None,None]+torch.tensor(mean)[:,None,None])*255).clamp(0,255).round().to(torch.uint8).permute(1,2,0).numpy()
  assert np.array_equal(recovered,stored_array),'actual Dataset tensor differs from saved input'
  contained=ImageOps.contain(image,(224,224),method=Image.Resampling.BICUBIC);w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
  tests=[]
  for fraction in (.25,.5,.75):
   cx=fraction*(image.width-1);cy=fraction*(image.height-1);radius=max(image.width/w,image.height/h)*2
   marker=Image.new('F',image.size,0);ImageDraw.Draw(marker).ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=1)
   padded=ImageOps.pad(marker,(224,224),method=Image.Resampling.BICUBIC,color=0)
   # The inverse crop/resize is the actual renderer's mapping. This marker is not an AI prediction.
   restored=padded.crop((left,top,left+w,top+h)).resize(image.size,Image.Resampling.BILINEAR)
   mass=np.maximum(np.asarray(restored,dtype=np.float64),0);total=mass.sum()
   actual_x=float((mass.sum(axis=0)*np.arange(image.width)).sum()/total);actual_y=float((mass.sum(axis=1)*np.arange(image.height)).sum()/total)
   dx=actual_x-cx;dy=actual_y-cy;within=abs(dx)<=image.width/w+1 and abs(dy)<=image.height/h+1
   tests.append(dict(expectedOriginalXY=[cx,cy],restoredCentroidXY=[actual_x,actual_y],originalPixelErrorXY=[dx,dy],inputPixelErrorXY=[dx*w/image.width,dy*h/image.height],withinOneInputPixelPerAxis=within))
   assert within,'inverse coordinate error exceeds the predefined one-input-pixel quantization allowance'
  data=json.loads(Path(sample['json_path']).read_text(encoding='utf-8-sig'));label_image=data['images'][0]
  assert label_image['file_name'].lower()==path.name.lower()
  boxes=[ann['bbox'] for ann in data.get('annotations',[]) if isinstance(ann.get('bbox'),list) and len(ann['bbox'])==4]
  display=image.copy();display.thumbnail((1400,1000));display.save(folder/'original.jpg',quality=92);expected.save(folder/'input224.png')
  label_preview(image,boxes,folder/'source_bbox_as_is.jpg')
  candidates=['source_bbox_as_is.jpg']
  if orientation in transpose and list(raw_size)==[label_image['width'],label_image['height']]:
   mask=Image.new('L',tuple(raw_size));draw=ImageDraw.Draw(mask)
   for xx,yy,ww,hh in boxes:draw.rectangle((xx,yy,xx+ww,yy+hh),fill=255)
   mask=mask.transpose(transpose[orientation]);bbox=mask.getbbox()
   if bbox:label_preview(image,[(bbox[0],bbox[1],bbox[2]-bbox[0],bbox[3]-bbox[1])],folder/'source_bbox_if_raw_orientation.jpg');candidates.append('source_bbox_if_raw_orientation.jpg')
  row=dict(id=sid,sourceSHA256=sample['imageSHA256'],EXIFOrientation=orientation,rawSize=raw_size,displaySize=list(image.size),saved224PixelsExactlyReproduced=True,actualDatasetTensorPixelsExactlyReproduced=True,containedInputSize=[w,h],paddingXY=[left,top],coordinateTests=tests,sourceBBox=boxes,sourceLabelImageSize=[label_image['width'],label_image['height']],labelCoordinateFrameCertified=False,approximate14GridSpacingInOriginalPixels=[image.width/w*16,image.height/h*16])
  report['samples'].append(row)
  sections.append('<section><h2>'+sid+'</h2><p>EXIF '+str(orientation)+' / 모델 입력과 저장된 224 이미지의 픽셀 일치 확인. 초록 상자는 원천 라벨이며 실제 결함 위치로 확정하지 않았습니다.</p><div class="grid">')
  assets=[('original.jpg','원본 표시'),('input224.png','실제 모델 입력 224')]+[(filename,'원천 BBOX: '+('표시 좌표에 그대로 표시' if 'as_is' in filename else '원본 좌표라고 가정 후 EXIF 변환')) for filename in candidates]
  for filename,title in assets:sections.append(f'<figure><a href="{sid}/{filename}" target="_blank"><img src="{sid}/{filename}"></a><figcaption>{html.escape(title)}</figcaption></figure>')
  sections.append('</div><p>14×14 한 칸의 원본 환산 간격: 약 '+str(round(row['approximate14GridSpacingInOriginalPixels'][0]))+'×'+str(round(row['approximate14GridSpacingInOriginalPixels'][1]))+'픽셀. 이는 모델의 실제 위치 오차나 결함 경계 정확도는 아닙니다.</p></section>')
  print('GEOMETRY_AUDIT',sid,'EXIF',orientation,'PIXELS_EXACT',True,'ROUNDTRIPS',len(tests),flush=True)
 report['allCoordinateRoundTripsPassed']=all(t['withinOneInputPixelPerAxis'] for r in report['samples'] for t in r['coordinateTests'])
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAM 좌표 점검</title><style>body{font-family:Malgun Gothic,sans-serif;max-width:1500px;margin:24px auto;padding:0 20px;background:#f3f6fa;line-height:1.7}section,header{background:white;padding:20px;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}figure{margin:0;background:#eaf0f6}img{width:100%;display:block}figcaption{padding:10px}</style><header><h1>좌표·입력 점검과 원천 라벨 참고</h1><p>모델을 새로 추론하거나 CAM을 옮기지 않았습니다. 실제 입력 픽셀과 좌표 복원 구현을 점검했습니다. 원천 BBOX는 초록색 참고 표시이며, 정확한 결함 라벨인지 사람 확인이 필요합니다. 인공 표식 왕복 시험은 수치 검사용으로만 사용했고 AI 결과처럼 표시하지 않았습니다.</p></header>'+''.join(sections)+'</html>'
 (out/'index.html').write_text(page)
 print('COORDINATE_AUDIT_COMPLETE',out,flush=True)

if __name__=='__main__':main()
