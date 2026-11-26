"""Prepare supplementary capture review of the existing sixteen cases; no inference."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1]
def main():
 source=ROOT/'ai_api/verification/framing_20261016T164416_557780Z/source.json'
 prior=Path('/path/to/private-user/다운로드/framing_review_2026-10-16T16-56-43.793Z.json')
 samples=json.loads(source.read_text())['candidates'];review=json.loads(prior.read_text())
 assert review['candidateHashes']==[s['imageSha256'] for s in samples]
 out=ROOT/'ai_api/verification'/('capture_review_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir()
 cases=[]
 for s in samples:
  path=Path(s['imagePath']);assert hashlib.sha256(path.read_bytes()).hexdigest()==s['imageSha256']
  with Image.open(path) as im:image=ImageOps.exif_transpose(im).convert('RGB')
  small=ImageOps.pad(image,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104));small.save(out/(s['id']+'_224.png'))
  image.thumbnail((1000,1000));image.save(out/(s['id']+'_original.jpg'),quality=94)
  cases.append(dict(id=s['id'],imagePath=s['imagePath'],imageSHA256=s['imageSha256'],originalUrl=s['originalUrl'],prior=review['state']['cases'][s['id']]))
 data=dict(schema='door-capture-supplement-v1',scopeStatus='pending_user_confirmation',source=str(source),sourceSHA256=hashlib.sha256(source.read_bytes()).hexdigest(),priorReview=str(prior),priorReviewSHA256=hashlib.sha256(prior.read_bytes()).hexdigest(),cases=cases)
 (out/'source.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 template=Path(__file__).with_name('capture_review_template.html').read_text();(out/'index.html').write_text(template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c')))
 print('[CAPTURE REVIEW]',out/'index.html')
if __name__=='__main__':main()
