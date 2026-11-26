"""Consistent DB + asset backup, then read-only comparison. Never starts/stops a service."""
import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen

BASE=Path(__file__).resolve().parent
STORAGE=BASE/'storage'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def rows(path):
    c=sqlite3.connect(f'file:{path}?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:
        c.execute('BEGIN')
        result={table:[dict(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY id')] for table in ('inspections','reviews')}
        result['integrity']=c.execute('PRAGMA integrity_check').fetchone()[0]
        result['foreign_key_issues']=[list(r) for r in c.execute('PRAGMA foreign_key_check')]
        return result
    finally:c.close()


def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2))


def prepare():
    dest=BASE/'backups'/datetime.now().strftime('restart_%Y%m%d_%H%M%S_%f');dest.mkdir(parents=True,exist_ok=False)
    print('[백업 시작] '+str(dest),flush=True)
    source=sqlite3.connect(f'file:{STORAGE}/history.sqlite3?mode=ro',uri=True,timeout=30)
    target=sqlite3.connect(dest/'history.sqlite3')
    try:source.backup(target,pages=256)
    finally:target.close();source.close()
    snapshot=rows(dest/'history.sqlite3')
    if snapshot['integrity']!='ok' or snapshot['foreign_key_issues']:raise RuntimeError('SQLite backup integrity failure')
    assets=[]
    for item in snapshot['inspections']:
        folder=STORAGE/'records'/item['id']
        for name in ('upload.bin','original.png','preview.jpg'):
            if not (folder/name).is_file():raise RuntimeError(f'Missing required asset: {folder/name}')
        for file in sorted(folder.iterdir()):
            if not file.is_file():continue
            relative=file.relative_to(STORAGE);out=dest/'assets'/relative;out.parent.mkdir(parents=True,exist_ok=True)
            for attempt in range(3):
                before=file.stat();shutil.copy2(file,out);digest=sha(out);after=file.stat()
                if (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns) and digest==sha(file):break
            else:raise RuntimeError(f'Asset changed while copying: {file}; backup not marked complete')
            assets.append(dict(path=str(relative),size=out.stat().st_size,sha256=digest))
    latest=sorted(snapshot['inspections'],key=lambda r:(r['created_at'],r['id']),reverse=True)[:5]
    state=dict(status='backup_complete',captured_at=datetime.now(timezone.utc).isoformat(),
        storage=str(STORAGE),sqlite_backup_method='sqlite3.Connection.backup; source opened read-only',
        database_sha256=sha(dest/'history.sqlite3'),snapshot=snapshot,assets=assets,
        inspection_count=len(snapshot['inspections']),review_count=len(snapshot['reviews']),
        recent_ids=[r['id'] for r in latest],recent_created_at=[r['created_at'] for r in latest])
    dump(dest/'before.json',state)
    print(json.dumps({k:v for k,v in state.items() if k not in ('snapshot','assets')},ensure_ascii=False,indent=2),flush=True)
    print(f'[백업 완료] DB 무결성 ok / 사진·CAM 포함 {len(assets)}개 파일\nBACKUP: {dest}',flush=True)
    return dest


def verify(dest,http=True):
    baseline=json.loads((dest/'before.json').read_text());old=baseline['snapshot'];current=rows(STORAGE/'history.sqlite3')
    missing=[];changed=[];added={}
    for table in ('inspections','reviews'):
        new={r['id']:r for r in current[table]};old_ids={r['id'] for r in old[table]}
        for item in old[table]:
            if item['id'] not in new:missing.append(dict(table=table,id=item['id']))
            elif item!=new[item['id']]:changed.append(dict(table=table,id=item['id'],fields=[k for k in item if item[k]!=new[item['id']][k]]))
        added[table]=[r['id'] for r in current[table] if r['id'] not in old_ids]
    asset_failures=[];backup_failures=[]
    if sha(dest/'history.sqlite3')!=baseline['database_sha256']:backup_failures.append('backup DB hash mismatch')
    for asset in baseline['assets']:
        for parent,failures in ((STORAGE,asset_failures),(dest/'assets',backup_failures)):
            path=parent/asset['path']
            if not path.is_file() or sha(path)!=asset['sha256']:failures.append(asset['path'])
    result=dict(checked_at=datetime.now(timezone.utc).isoformat(),backup=str(dest),
        before_inspections=baseline['inspection_count'],after_inspections=len(current['inspections']),
        before_reviews=baseline['review_count'],after_reviews=len(current['reviews']),recent_ids_before=baseline['recent_ids'],
        missing_rows=missing,changed_rows=changed,added_rows=added,asset_files_checked=len(baseline['assets']),
        changed_or_missing_assets=asset_failures,backup_failures=backup_failures,
        sqlite_integrity=current['integrity'],foreign_key_issues=current['foreign_key_issues'],
        existing_records_preserved=not(missing or changed or asset_failures or backup_failures) and current['integrity']=='ok' and not current['foreign_key_issues'],
        http_verified=False,browser_verified=False,container_restart_verified=False)
    if http:
        try:
            def get(path):
                with urlopen('http://127.0.0.1:8765'+path,timeout=30) as r:return r.read()
            health=json.loads(get('/api/health'))
            if not health.get('ready'):raise RuntimeError('GPU service is not ready')
            api_errors=[]
            for item in old['inspections']:
                data=json.loads(get('/api/records/'+item['id']))
                expected=json.loads(item['prediction_json']) if item['prediction_json'] else None
                previous_reviews=[r for r in old['reviews'] if r['inspection_id']==item['id']]
                if data['id']!=item['id'] or data['prediction']!=expected or any(r not in data['reviews'] for r in previous_reviews):
                    api_errors.append(item['id'])
                if 'review_state' not in data:api_errors.append(item['id']+': updated API not loaded')
            http_assets=0
            for asset in baseline['assets']:
                path=Path(asset['path']);name=path.name
                if name not in ('preview.jpg','original.png','cam0.png','cam1.png'):continue
                ident=path.parent.name;blob=get(f'/assets/{ident}/{name}');http_assets+=1
                if hashlib.sha256(blob).hexdigest()!=asset['sha256']:api_errors.append(asset['path'])
            js=get('/app.js').decode()
            if 'replaceSelection' not in js or 'sameRecord' not in js:api_errors.append('updated UI code not served')
            result.update(http_verified=not api_errors,http_errors=api_errors,http_asset_files_checked=http_assets,
                gpu=health['model']['gpu'],updated_ui_served='replaceSelection' in js,updated_api_loaded=not any('API not loaded' in e for e in api_errors))
        except Exception as e:result['http_error']=str(e)
    result['note']='Read-only DB/files/API verification. No service restart is performed or inferred by this script; browser viewing is separate. Startup self_check may append new rows.'
    output=dest/('verification_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json');dump(output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2));print('VERIFICATION: '+str(output))
    if not result['existing_records_preserved'] or (http and not result['http_verified']):raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--verify',type=Path);p.add_argument('--offline',action='store_true');args=p.parse_args()
    if args.prepare:prepare()
    else:verify(args.verify.resolve(),not args.offline)
