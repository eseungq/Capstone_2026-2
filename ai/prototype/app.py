"""Local door inspection prototype; stdlib HTTP + SQLite, GPU engine loaded once."""
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import threading
import traceback
import uuid
import warnings
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from PIL import Image,ImageOps,UnidentifiedImageError

MAX_BYTES=40*1024*1024
MAX_PIXELS=120_000_000
Image.MAX_IMAGE_PIXELS=MAX_PIXELS
STATIC=Path(__file__).parent/'static'


def now(): return datetime.now(timezone.utc).isoformat()


class Problem(Exception):
    def __init__(self,message,status=400): self.message,self.status=message,status


class Store:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'records').mkdir(exist_ok=True)
        self.db=self.root/'history.sqlite3'
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS inspections(
                id TEXT PRIMARY KEY,created_at TEXT NOT NULL,filename TEXT NOT NULL,
                upload_sha256 TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
                prediction_json TEXT,inferred_at TEXT);
                CREATE TABLE IF NOT EXISTS reviews(
                id INTEGER PRIMARY KEY AUTOINCREMENT,inspection_id TEXT NOT NULL REFERENCES inspections(id),
                reviewed_at TEXT NOT NULL,judgment TEXT NOT NULL CHECK(judgment IN ('양품','불량품','판단 보류')),
                note TEXT NOT NULL,actor TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS review_inspection ON reviews(inspection_id,id);''')
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
        try:
            with c: yield c
        finally: c.close()
    def directory(self,ident):
        if len(ident)!=32 or any(x not in '0123456789abcdef' for x in ident): raise Problem('검사 ID가 올바르지 않습니다.',404)
        return self.root/'records'/ident
    def get(self,ident):
        self.directory(ident)
        with self.connect() as c:
            row=c.execute('SELECT * FROM inspections WHERE id=?',(ident,)).fetchone()
            if row is None: raise Problem('검사 이력이 없습니다.',404)
            reviews=[dict(r) for r in c.execute('SELECT * FROM reviews WHERE inspection_id=? ORDER BY id',(ident,))]
        result=dict(row);result['prediction']=json.loads(result.pop('prediction_json')) if row['prediction_json'] else None
        result['reviews']=reviews;result['review']=reviews[-1] if reviews else None
        result['review_state']='not_reviewed' if not reviews else ('deferred' if reviews[-1]['judgment']=='판단 보류' else 'reviewed')
        result['worker_status']='작업자 미확인' if not reviews else ('작업자 판단 보류' if reviews[-1]['judgment']=='판단 보류' else '작업자 확인 완료')
        result['preview_url']=f'/assets/{ident}/preview.jpg'
        result['original_url']=f'/assets/{ident}/original.png'
        return result
    def listing(self,offset):
        with self.connect() as c:
            ids=[r[0] for r in c.execute('SELECT id FROM inspections ORDER BY created_at DESC,id DESC LIMIT 50 OFFSET ?',(offset,))]
            total=c.execute('SELECT COUNT(*) FROM inspections').fetchone()[0]
        return dict(items=[self.get(i) for i in ids],total=total,offset=offset)
    def upload(self,blob,filename):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(blob)) as source:
                    if source.format not in ('JPEG','PNG','WEBP'): raise Problem('JPEG·PNG·WebP 사진만 지원합니다.')
                    if getattr(source,'n_frames',1)!=1: raise Problem('움직이는 이미지는 지원하지 않습니다.')
                    if source.width*source.height>MAX_PIXELS: raise Problem('이미지가 너무 큽니다. 최대 1억 2천만 픽셀입니다.',413)
                    source.verify()
                with Image.open(io.BytesIO(blob)) as source:
                    original=ImageOps.exif_transpose(source).convert('RGB');original.load()
        except Problem: raise
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning) as e:
            raise Problem('사진을 읽을 수 없습니다. 손상 파일 또는 지원 범위를 벗어난 이미지입니다.') from e
        ident=uuid.uuid4().hex;dest=self.directory(ident);dest.mkdir()
        try:
            (dest/'upload.bin').write_bytes(blob)
            original.save(dest/'original.png')
            preview=original.copy();preview.thumbnail((1200,1200),Image.Resampling.LANCZOS);preview.save(dest/'preview.jpg',quality=92)
            with self.connect() as c:
                c.execute('INSERT INTO inspections(id,created_at,filename,upload_sha256,width,height) VALUES(?,?,?,?,?,?)',
                    (ident,now(),filename,hashlib.sha256(blob).hexdigest(),original.width,original.height))
        except Exception:
            shutil.rmtree(dest);raise
        return self.get(ident)
    def save_prediction(self,ident,result):
        with self.connect() as c:
            c.execute('UPDATE inspections SET prediction_json=?,inferred_at=? WHERE id=? AND prediction_json IS NULL',
                (json.dumps(result,ensure_ascii=False,allow_nan=False),now(),ident))
        return self.get(ident)
    def review(self,ident,judgment,note,actor='worker'):
        if not self.get(ident)['prediction']: raise Problem('모델 검사 실행 후 작업자 판단을 저장하세요.',409)
        if judgment not in ('양품','불량품','판단 보류'): raise Problem('작업자 판단을 선택하세요.')
        if actor not in ('worker','self_check'): raise Problem('확인 주체가 올바르지 않습니다.')
        if not isinstance(note,str) or len(note)>4000: raise Problem('메모는 4,000자 이내로 입력하세요.')
        with self.connect() as c:
            c.execute('INSERT INTO reviews(inspection_id,reviewed_at,judgment,note,actor) VALUES(?,?,?,?,?)',(ident,now(),judgment,note,actor))
        return self.get(ident)


class Service:
    def __init__(self,root,engine):
        self.store=Store(root);self.engine=engine;self.lock=threading.Lock();self.token=secrets.token_urlsafe(32)
    def predict(self,ident):
        with self.lock:
            item=self.store.get(ident)
            if item['prediction']: return item
            if self.engine is None: raise Problem('GPU 모델이 준비되지 않았습니다. 대체 예측을 만들지 않습니다.',503)
            result=self.engine.predict(self.store.directory(ident)/'upload.bin')
            return self.store.save_prediction(ident,result)
    def explain(self,ident,cls):
        if cls not in (0,1): raise Problem('설명 대상 클래스를 선택하세요.')
        with self.lock:
            item=self.store.get(ident)
            if not item['prediction']: raise Problem('검사 실행 후 참고 영역을 요청하세요.',409)
            if self.engine is None: raise Problem('GPU 모델이 준비되지 않았습니다.',503)
            if item['prediction']['model']['model_sha256']!=self.engine.metadata['model_sha256']:
                raise Problem('해당 이력과 현재 모델이 달라 참고 영역을 생성할 수 없습니다.',409)
            dest=self.store.directory(ident)
            cached=dest/f'cam{cls}.json'
            info=json.loads(cached.read_text()) if cached.exists() else self.engine.explain(dest/'upload.bin',dest,cls)
            return dict(**info,inspection_id=ident,overlay_url=f'/assets/{ident}/{info["overlay"]}' if info['overlay'] else None)


class Handler(BaseHTTPRequestHandler):
    server_version='DoorPrototype/1.0'
    def log_message(self,fmt,*args): print('[HTTP] '+fmt%args,flush=True)
    @property
    def service(self): return self.server.service
    def send(self,status,blob,kind='application/json; charset=utf-8'):
        if not isinstance(blob,bytes): blob=json.dumps(blob,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(blob)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(blob)
    def body(self,max_size):
        try: size=int(self.headers.get('Content-Length','-1'))
        except ValueError: raise Problem('요청 크기를 확인할 수 없습니다.')
        if size<1 or size>max_size: raise Problem('파일은 40MiB 이하, JSON 요청은 16KiB 이하로 제한됩니다.',413)
        data=self.rfile.read(size)
        if len(data)!=size: raise Problem('업로드가 중단되었습니다.')
        return data
    def guard(self,write=False):
        if self.headers.get('Host','') not in ('127.0.0.1:8765','localhost:8765',f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            raise Problem('로컬 주소로 접속하세요.',403)
        if write and not secrets.compare_digest(self.headers.get('X-Door-Token',''),self.service.token): raise Problem('페이지를 새로 열고 다시 시도하세요.',403)
    def do_GET(self): self.dispatch(False)
    def do_POST(self): self.dispatch(True)
    def dispatch(self,write):
        try:
            self.connection.settimeout(120)
            self.guard(write)
            parsed=urlparse(self.path);parts=parsed.path.strip('/').split('/')
            if not write and parsed.path=='/':
                page=(STATIC/'index.html').read_text().replace('__TOKEN__',self.service.token)
                return self.send(200,page.encode(),'text/html; charset=utf-8')
            if not write and parsed.path in ('/app.js','/style.css'):
                kind='text/javascript; charset=utf-8' if parsed.path.endswith('.js') else 'text/css; charset=utf-8'
                return self.send(200,(STATIC/parts[0]).read_bytes(),kind)
            if not write and parsed.path=='/api/health':
                return self.send(200,dict(ready=self.service.engine is not None,model=self.service.engine.metadata if self.service.engine else None))
            if not write and parts[:2]==['api','records']:
                if len(parts)==3: return self.send(200,self.service.store.get(parts[2]))
                if len(parts)!=2: raise Problem('요청 경로가 없습니다.',404)
                try: offset=max(0,int(parse_qs(parsed.query).get('offset',['0'])[0]))
                except ValueError: raise Problem('목록 위치가 잘못되었습니다.')
                return self.send(200,self.service.store.listing(offset))
            if not write and len(parts)==3 and parts[0]=='assets':
                self.service.store.get(parts[1])
                if parts[2] not in ('preview.jpg','original.png','cam0.png','cam1.png'): raise Problem('파일이 없습니다.',404)
                file=self.service.store.directory(parts[1])/parts[2]
                if not file.is_file(): raise Problem('파일이 없습니다.',404)
                return self.send(200,file.read_bytes(),'image/jpeg' if file.suffix=='.jpg' else 'image/png')
            if write and parsed.path=='/api/uploads':
                filename=unquote(self.headers.get('X-File-Name','upload'))[:240].replace('\\','/').split('/')[-1]
                blob=self.body(MAX_BYTES)
                with self.service.lock: result=self.service.store.upload(blob,filename)
                return self.send(201,result)
            if write and len(parts)==4 and parts[:2]==['api','records']:
                ident,action=parts[2:]
                try: data=json.loads(self.body(16*1024))
                except (json.JSONDecodeError,UnicodeDecodeError): raise Problem('요청 JSON이 올바르지 않습니다.')
                if not isinstance(data,dict): raise Problem('요청 JSON 객체가 필요합니다.')
                if action=='inspect': return self.send(200,self.service.predict(ident))
                if action=='review': return self.send(200,self.service.store.review(ident,data.get('judgment'),data.get('note',''),data.get('actor','worker')))
                if action=='cam':
                    cls=data.get('target_class')
                    if type(cls) is not int: raise Problem('대상 클래스는 0 또는 1입니다.')
                    return self.send(200,self.service.explain(ident,cls))
            raise Problem('요청 경로가 없습니다.',404)
        except Problem as e: self.send(e.status,dict(error=e.message))
        except Exception:
            traceback.print_exc()
            self.send(500,dict(error='처리에 실패했습니다. 임의 예측으로 대체하지 않았습니다. 서버 로그를 확인하세요. 참고 영역 실패 시 기존 예측과 저장 기능은 유지됩니다.'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--storage',type=Path,default=Path(__file__).parent/'storage');parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    # Bind first so an occupied port cannot create a second loaded GPU model.
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    server.daemon_threads=True
    try:
        from engine import Engine
        print('[시작] 도어 모델 1회 로딩',flush=True)
        server.service=Service(args.storage,Engine())
        if args.self_check:
            from check_flow import check
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try: check(f'http://127.0.0.1:{args.port}',server.service)
            except Exception:
                server.shutdown();thread.join();raise
            print('[서비스 준비] http://127.0.0.1:8765 / 종료: Ctrl+C',flush=True)
            try: thread.join()
            finally: server.shutdown()
        else:
            print(f'[서비스 준비] http://127.0.0.1:{args.port} / 종료: Ctrl+C',flush=True)
            server.serve_forever()
    except KeyboardInterrupt: print('[종료] 이력은 저장 폴더에 보존됩니다.',flush=True)
    finally: server.server_close()


if __name__=='__main__': main()
