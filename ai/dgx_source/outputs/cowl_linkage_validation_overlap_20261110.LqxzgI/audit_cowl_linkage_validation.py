import csv
from collections import Counter, defaultdict
import hashlib, io, json, sys, tarfile
from pathlib import Path
from PIL import Image, ImageOps
from cowl_model.audit_similarity import dhash

def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def source_stat(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


def inventory(image_path, label_path):
    images = {}
    with tarfile.open(image_path, "r:") as archive:
        for m in archive:
            if not m.isfile() or Path(m.name).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            ident = Path(m.name).stem
            assert ident not in images
            images[ident] = (m.offset_data, m.size)
    rows = {}
    with tarfile.open(label_path, "r:") as archive:
        for m in archive:
            if not m.isfile() or Path(m.name).suffix != ".json":
                continue
            label = archive.extractfile(m).read()
            data = json.loads(label)
            annotations = data["annotations"]
            if 205 not in {a["category_id"] for a in annotations}:
                continue
            image, = data["images"]
            ident = Path(m.name).stem
            assert ident not in rows and ident == Path(image["file_name"]).stem
            assert {a["category_id"] for a in annotations} == {205}
            assert {a["attributes"]["part"] for a in annotations} == {"카울커버"}
            quality, = {a["attributes"]["quality"] for a in annotations}
            offset, size = images[ident]
            rows[ident] = dict(image_id=ident,image_archive=str(image_path),offset=offset,size=size,
                               class_id={"양품":"0","불량품":"1"}[quality],label_sha256=digest(label),
                               captured_at=image.get("date_captured"))
    assert len(rows) == 1254, len(rows)
    return rows


def audit(rows, train_fingerprints, out):
    train = list(map(json.loads, train_fingerprints.read_bytes().splitlines()))
    assert len(train) == 20386 and len({r["image_id"] for r in train}) == len(train)
    exact_source, exact_pixels = defaultdict(list), defaultdict(list)
    train_near = []
    for r in train:
        exact_source[r["source_sha256"]].append(r["image_id"])
        exact_pixels[r["display_sha256"]].append(r["image_id"])
        train_near.append((int(r["dhash64"]),r["image_id"]))
    cross = {}
    parent = {i:i for i in rows}
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(a,b):
        a,b = sorted((root(a),root(b)))
        parent[b] = a
    prior = []
    exact_groups = defaultdict(list)
    archive_path, = {r["image_archive"] for r in rows.values()}
    with Path(archive_path).open("rb") as archive:
        for n,row in enumerate(sorted(rows.values(),key=lambda r:r["offset"]),1):
            ident = row["image_id"]
            archive.seek(row["offset"])
            blob = archive.read(row["size"])
            assert len(blob) == row["size"]
            with Image.open(io.BytesIO(blob)) as raw:
                display = ImageOps.exif_transpose(raw).convert("RGB")
            s = digest(blob)
            d = digest(str(display.size).encode()+display.tobytes())
            h = dhash(display)
            same = set(exact_source[s]) | set(exact_pixels[d])
            near = [i for f,i in train_near if (h^f).bit_count() <= 8 and i not in same]
            cross[ident] = dict(exact=sorted(same),near=sorted(near))
            exact_groups[d].append(ident)
            row.update(image_sha256=s, display_sha256=d)
            for f,i in prior:
                if (h^f).bit_count() <= 8:
                    join(ident,i)
            prior.append((h,ident))
            if n % 250 == 0:
                print("OVERLAP", n, "/", len(rows), flush=True)
    held = {}
    for members in exact_groups.values():
        if len(members) > 1:
            for i in members[1:]:
                join(members[0],i)
            if len({rows[i]["class_id"] for i in members}) > 1:
                held.update({i:"validation_exact_label_conflict" for i in members})
            else:
                held.update({i:"validation_exact_duplicate_copy" for i in sorted(members)[1:]})
    for ident, row in rows.items():
        row["group_id"] = root(ident)
        if cross[ident]["exact"]:
            held[ident] = "exact_overlap_with_training_pool"
    manifest = [dict(**r, excluded=held.get(i), cross_near=bool(cross[i]["near"]))
                for i,r in sorted(rows.items())]
    write_json(out/"overlap_matches.json", cross)
    write_json(out/"frozen_evaluation_manifest.json",manifest)
    return manifest, Counter(held.values())



def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")

def main(out):
    train = Path(json.loads(Path('cowl_model/latest_full_similarity.json').read_bytes())['directory'])
    fp = train/'fingerprints.jsonl'
    audit_summary = json.loads((train/'summary.json').read_bytes())
    assert audit_summary['decode_errors']==0 and audit_summary['fingerprinted']==20386
    types={r['image_id']:r['type'] for r in map(json.loads,fp.read_bytes().splitlines())}
    assert len(types)==20386
    prep = Path('outputs/cowl_linkage_split_20261109.SyXrpy')
    config_bytes=(prep/'config.json').read_bytes()
    assert digest(config_bytes)=='de12f7bf0c7bbd1b58e1675990fd2e3e1523d89f74788f27400bad9db7d808a0'
    conf=json.loads(config_bytes)
    roles={}
    for role, spec in conf['manifests'].items():
        path=Path(spec['path'])
        assert digest(path.read_bytes())==spec['sha256']
        with path.open(encoding='utf-8-sig',newline='') as file:
            for row in csv.DictReader(file):
                assert row['image_id'] not in roles
                roles[row['image_id']]=role
    ip,=Path('downloads').glob('aihub/*/01.*/2.Validation/*/VS_6.*.tar')
    lp,=Path('downloads').glob('aihub/*/01.*/2.Validation/*/VL_6.*.tar')
    before={str(p):source_stat(p) for p in (ip,lp)}
    rows=inventory(ip.resolve(),lp.resolve())
    manifest, holds=audit(rows,fp,out)
    assert before=={str(p):source_stat(p) for p in (ip,lp)}
    matches=json.loads((out/'overlap_matches.json').read_bytes())
    primary=[r for r in manifest if r['excluded'] is None]
    strict=[r for r in primary if not r['cross_near']]
    exact=[]
    near_counts=Counter()
    for r in manifest:
        m=matches[r['image_id']]
        for match in m['exact']:
            exact.append(dict(validation_id=r['image_id'],validation_class=r['class_id'],training_id=match,
                              training_type=types[match],linkage_split=roles.get(match,'outside_linkage_split')))
        if r['excluded'] is None:
            near_counts.update({roles.get(i,'outside_linkage_split') for i in m['near']})
    def counts(rows):
        y=Counter(r['class_id'] for r in rows)
        return dict(total=len(rows),good=y['0'],defect=y['1'])
    report=dict(scope='카울커버 연계 불량(205)',comparison_training_photos=len(types),
                original=counts(manifest),primary=counts(primary),sensitivity=counts(strict),
                exact_cross_split_photos=sum(bool(m['exact']) for m in matches.values()),exact_pairs=exact,
                primary_photos_with_cross_near=len(primary)-len(strict),
                near_by_training_role=near_counts,exclusions=holds,
                internal_exact_extra_copies=sum(len(g)-1 for g in exact_groups_by_hash(manifest).values() if len(g)>1),
                internal_exact_conflict_groups=sum(len({r['class_id'] for r in g})>1 for g in exact_groups_by_hash(manifest).values()),
                cross_near_method='64-bit dHash Hamming distance <= 8; candidate, no visual confirmation',
                manifest_sha256=digest((out/'frozen_evaluation_manifest.json').read_bytes()),
                match_sha256=digest((out/'overlap_matches.json').read_bytes()),
                training_fingerprints_sha256=digest(fp.read_bytes()),model_inference=False)
    write_json(out/'linkage_validation_overlap_summary.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

def exact_groups_by_hash(rows):
    result=defaultdict(list)
    for row in rows:
        result[row['display_sha256']].append(row)
    return result

if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(strict=True))
