"""Read saved CAMs only. No inference, coordinate adjustment, or writes to user records."""
import hashlib
import html
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageChops

BASE=Path(__file__).resolve().parent

def main():
    dest=BASE/'audits'/datetime.now().strftime('connections_%Y%m%d_%H%M%S_%f');dest.mkdir()
    c=sqlite3.connect(f'file:{BASE}/storage/history.sqlite3?mode=ro',uri=True);c.row_factory=sqlite3.Row
    rows=[dict(r) for r in c.execute('SELECT * FROM inspections ORDER BY created_at DESC')]
    records=[];cards=[]
    for row in rows:
        folder=BASE/'storage/records'/row['id']
        for meta in sorted(folder.glob('cam*.json')):
            info=json.loads(meta.read_text());cls=info['target_class']
            raw=np.load(folder/f'cam{cls}_raw.npy',allow_pickle=False)
            assert raw.shape==(7,7) and np.isfinite(raw).all()
            with Image.open(folder/'upload.bin') as src:
                orientation=src.getexif().get(274,1);raw_size=src.size
                original=ImageOps.exif_transpose(src).convert('RGB')
            with Image.open(folder/'original.png') as saved:
                original_equal=ImageChops.difference(original,saved.convert('RGB')).getbbox() is None
            padded=ImageOps.pad(original,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104))
            contained=ImageOps.contain(original,(224,224),method=Image.Resampling.BICUBIC)
            w,h=contained.size;left,top=round((224-w)*0.5),round((224-h)*0.5)
            crop=[left,top,left+w,top+h]
            prefix=f'{row["id"]}_class{cls}'
            padded.save(dest/f'{prefix}_input.png')
            evidence=dict(inspection_id=row['id'],filename=row['filename'],target_class=cls,
                upload_sha256_matches=hashlib.sha256((folder/'upload.bin').read_bytes()).hexdigest()==row['upload_sha256'],
                exif_orientation=orientation,raw_size=list(raw_size),corrected_size=list(original.size),
                exif_original_pixels_match=original_equal,padding_crop=crop,
                metadata_crop_matches=info.get('padding_crop',crop)==crop,raw_map_shape=list(raw.shape),
                raw_map_finite=True,constant=info['constant'])
            pictures=f'<figure><figcaption>정규화 전 224×224 입력</figcaption><img width="224" height="224" src="{prefix}_input.png"></figure>'
            if not info['constant']:
                lo,hi=float(raw.min()),float(raw.max());norm=(raw-lo)/(hi-lo)
                full=np.asarray(Image.fromarray(norm.astype('float32')).resize((224,224),Image.Resampling.BILINEAR))
                heat=np.stack((full,np.zeros_like(full),1-full),axis=-1)*255
                input_overlay=(np.asarray(padded)*0.6+heat*0.4).clip(0,255).astype('uint8')
                Image.fromarray(input_overlay).save(dest/f'{prefix}_input_overlay.png')
                mapped=np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(original.size,Image.Resampling.BILINEAR))
                values=np.clip(mapped,0,1);heat=np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
                overlay=(np.asarray(original)*0.6+heat*0.4).clip(0,255).astype('uint8')
                with Image.open(folder/info['overlay']) as saved:
                    delta=np.abs(overlay.astype('int16')-np.asarray(saved).astype('int16'))
                y,x=np.unravel_index(np.argmax(mapped),mapped.shape)
                py,px=np.unravel_index(np.argmax(full),full.shape)
                ry,rx=np.unravel_index(np.argmax(raw),raw.shape)
                evidence.update(overlay_reconstruction_max_channel_difference=int(delta.max()),
                    overlay_pixels_match=not bool(delta.any()),raw_peak_xy=[int(rx),int(ry)],
                    padded_peak_xy=[int(px),int(py)],original_peak_xy=[int(x),int(y)])
                preview=Image.fromarray(overlay);preview.thumbnail((1100,1100),Image.Resampling.LANCZOS);preview.save(dest/f'{prefix}_original_overlay.jpg',quality=95)
                pictures+=f'<figure><figcaption>224 입력+동일 히트맵 (패딩 포함)</figcaption><img width="224" height="224" src="{prefix}_input_overlay.png"></figure><figure><figcaption>동일 히트맵의 패딩 제거 → EXIF 원본 좌표 오버레이</figcaption><img class="large" src="{prefix}_original_overlay.jpg"></figure>'
            else:pictures+='<p>0 또는 일정한 맵. 색상 오버레이 없음.</p>'
            records.append(evidence)
            cards.append(f'<article id="{row["id"]}"><h2>{html.escape(row["filename"])} · 검사 {row["id"]} · 클래스 {cls}</h2><div class="compare">{pictures}</div><pre>{html.escape(json.dumps(evidence,ensure_ascii=False,indent=2))}</pre></article>')
    import PIL
    summary=dict(scope='Saved CAM coordinate reconstruction only; no GPU inference, no manual shift, no writes to original records',
        diagnostic_versions=dict(Pillow=PIL.__version__,numpy=np.__version__),
        original_service_versions=json.loads(next(r['prediction_json'] for r in rows if r['prediction_json']))['model']['versions'],
        inspected_records=len(rows),inspected_cams=len(records),records=records)
    (dest/'coordinates.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (dest/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Grad-CAM 좌표 연결 확인</title><style>body{font:14px system-ui;margin:24px;background:#f3f5f8}article{background:white;padding:20px;margin:24px 0;overflow-wrap:anywhere}.compare{display:flex;align-items:start;gap:18px;flex-wrap:wrap}figure{margin:0}figcaption{font-size:12px;margin-bottom:10px;max-width:440px}.large{width:660px;max-width:100%}pre{white-space:pre-wrap}</style><h1>저장된 동일 히트맵의 좌표 연결 확인</h1><p>기존 7×7 원시 맵으로만 재구성. 재추론·위치 보정 없음. 결함 위치 검출 결과가 아님. 224 입력의 패딩을 제거한 후 원본으로 복원합니다.</p>'+''.join(cards))
    c.close()
    print(str(dest),flush=True)
    print(json.dumps(dict(cams=len(records),originals_all_match=all(r['exif_original_pixels_match'] for r in records),crops_all_match=all(r['metadata_crop_matches'] for r in records),overlays_all_match=all(r.get('overlay_pixels_match',True) for r in records)),ensure_ascii=False),flush=True)

if __name__=='__main__': main()
