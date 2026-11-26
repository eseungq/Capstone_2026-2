"""Reuse completed frame audit to prepare a four-type baseline experiment proposal."""
import csv,hashlib,json,math,random,tarfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from ai_api.duplicate_groups import components,read_csv,dump
ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'ai_api/verification/frame_audit_20261020T171709_051078Z'
ROLES=('train','model_selection','calibration_fit','policy_development')
RATIOS=(.70,.15,.075,.075)
TYPES=('실링 불량','외관 손상','헤밍 불량','홀 변형')

def group_split(rows,seed=42):
 strata=sorted({(r['defect_type'],r['class_id']) for r in rows})
 totals=Counter((r['defect_type'],r['class_id']) for r in rows);groups=defaultdict(list)
 for r in rows:groups[r['group_id']].append(r)
 order=sorted(groups,key=lambda g:(-len(groups[g]),hashlib.sha256(f'{seed}:{g}'.encode()).hexdigest()))
 counts={role:Counter() for role in ROLES};assigned={};role_sizes=Counter()
 for gid in order:
  vec=Counter((r['defect_type'],r['class_id']) for r in groups[gid])
  costs={}
  for role,ratio in zip(ROLES,RATIOS):
   cost=sum(((counts[role][k]+n-totals[k]*ratio)**2-(counts[role][k]-totals[k]*ratio)**2)/max(1,totals[k]*ratio) for k,n in vec.items())
   target=len(rows)*ratio;n=len(groups[gid]);cost+=.25*((role_sizes[role]+n-target)**2-(role_sizes[role]-target)**2)/max(1,target)
   costs[role]=cost
  role=min(ROLES,key=lambda r:(costs[r],ROLES.index(r)));assigned[gid]=role;counts[role].update(vec);role_sizes[role]+=len(groups[gid])
 result=[dict(r,split=assigned[r['group_id']]) for r in rows]
 for role in ROLES:
  if any(counts[role][k]==0 for k in strata):raise ValueError('Missing class/type in proposed role')
 return result

def main():
 audit=json.loads((AUDIT/'summary.json').read_text());source=AUDIT/'image_inventory.csv';rows=read_csv(source)
 if audit['status']!='complete' or len(rows)!=26101:raise ValueError('Expected complete original audit')
 for path,stat in audit['archiveStats'].items():
  p=Path(path)
  if p.stat().st_size!=stat['bytes'] or p.stat().st_mtime_ns!=stat['mtime_ns']:raise ValueError('Audited archive changed')
 labels_path=next(Path(p) for p in audit['archiveStats'] if '/라벨링데이터/' in p)
 if hashlib.sha256(labels_path.read_bytes()).hexdigest()!=audit['labelArchiveSHA256']:raise ValueError('Label archive changed')
 meta={}
 with tarfile.open(labels_path) as archive:
  for member in archive:
   if not member.isfile() or not member.name.endswith('.json'):continue
   raw=archive.extractfile(member).read();label=json.loads(raw.decode('utf-8-sig'));attrs=[a.get('attributes',{}) for a in label['annotations']]
   if any(a.get('part')!='프레임' for a in attrs):raise ValueError('Unexpected source part')
   meta[member.name]=dict(captured_at=label['images'][0]['date_captured'],label_sha256=hashlib.sha256(raw).hexdigest())
 offsets={}
 for path in sorted({r['imageArchive'] for r in rows}):
  with tarfile.open(path,'r:') as archive:
   for m in archive:
    if m.isfile():offsets[(path,m.name)]=(m.offset_data,m.size)
 # One representative per exact-byte group. Do not merge differently encoded images silently.
 exact=defaultdict(list)
 for r in rows:exact[r['imageSHA256']].append(r)
 reps=[];all_records=[]
 for digest,members in sorted(exact.items()):
  if len({m['sourceQuality'] for m in members})!=1:raise ValueError('Exact duplicate quality conflict')
  selected=min(members,key=lambda r:(r['imageArchive'],r['imageMember']))
  for m in members:all_records.append(dict(image_archive=m['imageArchive'],image_member=m['imageMember'],image_sha256=digest,representative_member=selected['imageMember'],action='representative' if m is selected else 'omit_exact_duplicate'))
  if selected['sourceTypes'] not in TYPES or selected['sourceQuality'] not in ('양품','불량품'):raise ValueError('Unresolved source label')
  offset,size=offsets[(selected['imageArchive'],selected['imageMember'])]
  reps.append(dict(image_id=digest,image_archive=selected['imageArchive'],image_member=selected['imageMember'],offset=offset,size=size,image_sha256=digest,label_archive=str(labels_path),label_member=selected['labelMember'],class_id={'양품':0,'불량품':1}[selected['sourceQuality']],source_quality=selected['sourceQuality'],defect_type=selected['sourceTypes'],captured_at=meta[selected['labelMember']]['captured_at'],label_sha256=meta[selected['labelMember']]['label_sha256']))
 # Conservative proposed capture sessions by type, adjacent source timestamps <=60s.
 edges=[];session_start={};by_type=defaultdict(list)
 for r in reps:by_type[r['defect_type']].append(r)
 for kind,items in by_type.items():
  anchor=None;previous=None
  for r in sorted(items,key=lambda r:(r['captured_at'],r['image_id'])):
   stamp=datetime.fromisoformat(r['captured_at'])
   if previous is None or (stamp-previous).total_seconds()>60:anchor=r['image_id']
   elif anchor!=r['image_id']:edges.append((anchor,r['image_id']))
   previous=stamp
 # Exact copies can carry capture timestamps in different sessions; connect all such sessions.
 digest_session_anchors=defaultdict(set)
 label_sessions=defaultdict(list)
 for r in rows:label_sessions[r['sourceTypes']].append(r)
 for kind,items in label_sessions.items():
  anchor_digest=None;previous=None
  for r in sorted(items,key=lambda r:(meta[r['labelMember']]['captured_at'],r['imageSHA256'])):
   stamp=datetime.fromisoformat(meta[r['labelMember']]['captured_at'])
   if previous is None or (stamp-previous).total_seconds()>60:anchor_digest=r['imageSHA256']
   edges.append((anchor_digest,r['imageSHA256']));previous=stamp
 groups=components([r['image_id'] for r in reps],edges);gid={p:'frame_'+hashlib.sha256('\n'.join(g).encode()).hexdigest() for g in groups for p in g}
 for r in reps:r['group_id']=gid[r['image_id']]
 split=group_split(reps);assert group_split(reps[::-1])==list(reversed(split))
 assert len({r['image_sha256'] for r in split})==len(split)==26040
 assigned=defaultdict(set)
 for r in split:assigned[r['group_id']].add(r['split'])
 assert all(len(v)==1 for v in assigned.values())
 output=ROOT/'outputs/frame_preparation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');output.mkdir(parents=True)
 def write(path,items):
  with path.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
 write(output/'all_candidates.csv',split);write(output/'original_image_ledger.csv',all_records)
 for role in ROLES:write(output/(role+'.csv'),[r for r in split if r['split']==role])
 counts=Counter((r['split'],r['defect_type'],r['class_id']) for r in split)
 with (output/'distribution.csv').open('w',newline='') as f:w=csv.writer(f);w.writerow(['split','defect_type','class_id','images']);w.writerows([(*k,v) for k,v in sorted(counts.items())])
 config=dict(status='prepared_exploratory_proposal',model_name='swin_tiny_patch4_window7_224.ms_in1k',pretrained=True,image_size=224,batch_size=8,epochs=20,learning_rate=1e-4,weight_decay=1e-4,seed=42,num_workers=0,amp=False,augmentation='none',selection='model_selection_f1',prediction_cutoff=.5,mean=[.485,.456,.406],std=[.229,.224,.225],fill=[124,116,104],class_mapping={'GOOD':0,'DEFECT':1},scope='Visible photographed inspection item; source type-specific quality. Not exhaustive whole-frame PASS/FAIL.',inspection_types=list(TYPES),grouping='exact-byte copies collapsed; proposed per-type adjacent source capture timestamps <=60s connected, including discarded exact copies',grouping_is_verified_physical_part_id=False,split_ratios=dict(zip(ROLES,RATIOS)),roles=dict(Counter(r['split'] for r in split)),groups=len(groups),largest_group=max(map(len,groups)),audit=str(AUDIT),audit_inventory_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),archive_stats=audit['archiveStats'],manifests={role:dict(path=str(output/(role+'.csv')),sha256=hashlib.sha256((output/(role+'.csv')).read_bytes()).hexdigest()) for role in ROLES},validation_archive_read=False,training_started=False,calibration_ready=False,policy_ready=False,passThreshold=None,limitations=['temporal session grouping heuristic is not verified physical independence','source labels not newly adjudicated; global binary policy is scoped to visible item','224 visibility and capture-condition confounding need validation','no independent final evaluation yet'])
 dump(output/'config.json',config);dump(output/'validation.json',dict(status='passed',originalImages=26101,representatives=26040,duplicatesOmitted=61,groupCrossings=0,shaCrossings=0,inputOrderInvariant=True,allRolesContainEveryTypeAndClass=True,trainingStarted=False))
 pointer=ROOT/'frame_model/latest_preparation.json';dump(pointer,dict(preparation=str(output),config=str(output/'config.json')))
 print(output);print('roles',config['roles'],'groups',config['groups'],'largest',config['largest_group'])
if __name__=='__main__':main()
