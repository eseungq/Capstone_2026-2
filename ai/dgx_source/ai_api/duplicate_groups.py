"""Prepare immutable-source duplicate groups; validate future split proposals only."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT/'ai_api/verification/data_audit_20261016T181906_711013Z'
REVIEW = ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z/user_similarity_review.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def components(paths, edges):
    parent = {p:p for p in paths}
    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p
    for a,b in edges:
        if a not in parent or b not in parent:
            raise ValueError('Evidence contains a path outside train/internal manifests')
        parent[find(a)] = find(b)
    groups = defaultdict(list)
    for p in sorted(paths): groups[find(p)].append(p)
    return sorted(groups.values())


def validate(groups, assignments):
    members = {p:g for g in groups for p in g['members']}
    seen, group_splits, errors = set(), defaultdict(set), []
    for row in assignments:
        path, split = row.get('image_path',''), row.get('split','').strip()
        if path in seen: errors.append(dict(type='duplicate_assignment',image_path=path))
        seen.add(path)
        if path not in members:
            errors.append(dict(type='unknown_image',image_path=path));continue
        group = members[path]
        if not split: errors.append(dict(type='empty_split',image_path=path))
        if group['labelConflict']:
            errors.append(dict(type='unresolved_label_conflict',groupId=group['groupId'],image_path=path))
        group_splits[group['groupId']].add(split)
    for gid,splits in group_splits.items():
        if len(splits)>1: errors.append(dict(type='group_crosses_splits',groupId=gid,splits=sorted(splits)))
    required = {p for p,g in members.items() if not g['labelConflict']}
    missing = sorted(required-seen)
    if missing: errors.append(dict(type='missing_nonconflict_images',count=len(missing),image_paths=missing))
    return dict(status='failed' if errors else 'passed',errors=errors,
                meaning='Known duplicate-group separation and coverage only; not physical-part independence or model evaluation')


def build(supplemental_reviews=()):
    sources = [ROOT/'outputs/manifests/door_train.csv',ROOT/'outputs/manifests/door_internal_validation.csv',
               AUDIT/'image_hashes.csv',REVIEW]+list(supplemental_reviews)
    hashes_before = {str(p):sha(p) for p in sources}
    rows=[]
    for split,p in zip(['train','internal_validation'],sources[:2]):
        rows.extend(dict(r,originalSplit=split) for r in read_csv(p))
    if Counter(r['originalSplit'] for r in rows) != {'train':11554,'internal_validation':2039}:
        raise ValueError('Unexpected manifest counts')
    paths = {r['image_path'] for r in rows}
    if len(paths)!=len(rows): raise ValueError('Repeated manifest paths')
    by_path={r['image_path']:r for r in rows}
    hash_rows=read_csv(sources[2])
    if len(hash_rows)!=len(rows) or {r['image_path'] for r in hash_rows}!=paths:
        raise ValueError('Hash audit does not cover current manifests')
    audit_summary=json.loads((AUDIT/'summary.json').read_text())
    for split,p in zip(['train','internal_validation'],sources[:2]):
        if sha(p)!=audit_summary['manifests'][split]['sha256']:
            raise ValueError('Manifest changed since original audit')
    digest_groups=defaultdict(list)
    for r in hash_rows:
        if not r['sha256']: raise ValueError('Missing image hash')
        digest_groups[r['sha256']].append(r['image_path'])
    edges=[]
    for digest,items in sorted(digest_groups.items()):
        for p in sorted(items)[1:]:
            edges.append(dict(a=sorted(items)[0],b=p,evidence='exact_file_sha256',sha256=digest))
    review=json.loads(REVIEW.read_text())
    reviewed_source=Path(review['source'])
    if sha(reviewed_source)!=review['sourceSHA256']: raise ValueError('Reviewed ordering changed')
    for r in review['records']:
        if r['judgment']=='user_confirmed_same_photo':
            edges.append(dict(a=r['train_image'],b=r['validation_image'],evidence='user_confirmed_same_photo',displayNumber=r['displayNumber']))
    for path in supplemental_reviews:
        extra=json.loads(path.read_text())
        if sha(Path(extra['source']))!=extra['sourceSHA256']:raise ValueError('Supplemental review source changed')
        for r in extra['records']:
            if r['judgment']=='user_confirmed_same_photo':
                edges.append(dict(a=r['train_image'],b=r['validation_image'],evidence='user_confirmed_same_photo',displayNumber=r['displayNumber'],reviewFile=str(path)))
    groups=[]
    for items in components(paths,[(e['a'],e['b']) for e in edges]):
        gid='door_'+hashlib.sha256('\n'.join(items).encode()).hexdigest()
        labels=sorted({int(by_path[p]['class_id']) for p in items})
        splits=sorted({by_path[p]['originalSplit'] for p in items})
        groups.append(dict(groupId=gid,members=items,classIds=labels,labelConflict=len(labels)>1,
                           originalSplits=splits,action='hold_for_label_resolution' if len(labels)>1 else 'keep_group_in_one_future_split'))
    output=ROOT/'ai_api/verification'/('duplicate_groups_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir()
    dump(output/'groups.json',groups);dump(output/'evidence_edges.json',edges)
    lookup={p:g for g in groups for p in g['members']}
    fields=list(rows[0])+['groupId','groupAction']
    with (output/'grouped_manifest.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in rows: writer.writerow(dict(r,groupId=lookup[r['image_path']]['groupId'],groupAction=lookup[r['image_path']]['action']))
    dump(output/'label_conflict_groups.json',[g for g in groups if g['labelConflict']])
    unchanged=all(sha(p)==hashes_before[str(p)] for p in sources)
    summary=dict(status='complete' if unchanged else 'source_changed',originalsModified=False,finalTestUsed=False,
                 sourceHashes=hashes_before,imageCount=len(rows),groupCount=len(groups),
                 duplicateGroups=sum(len(g['members'])>1 for g in groups),
                 labelConflictGroups=sum(g['labelConflict'] for g in groups),
                 heldImages=sum(len(g['members']) for g in groups if g['labelConflict']),
                 knownCrossSplitGroups=sum(len(g['originalSplits'])>1 for g in groups),
                 sourceHashesUnchanged=unchanged,splitApplied=False,
                 limitations='Known exact-file and user-confirmed links only; no final-test or physical-part independence claim')
    dump(output/'summary.json',summary)
    # Demonstrate detection against the preserved current split.
    dump(output/'existing_split_check.json',validate(groups,[dict(image_path=r['image_path'],split=r['originalSplit']) for r in rows]))
    print(json.dumps(dict(output=str(output),**summary),ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    builder=sub.add_parser('build')
    builder.add_argument('--supplemental-review',type=Path,action='append',default=[])
    check=sub.add_parser('check')
    check.add_argument('--groups',type=Path,required=True)
    check.add_argument('--proposal',type=Path,required=True,help='CSV with image_path and split columns')
    args=parser.parse_args()
    if args.command=='build': build(args.supplemental_review)
    else:
        result=validate(json.loads(args.groups.read_text()),read_csv(args.proposal))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
