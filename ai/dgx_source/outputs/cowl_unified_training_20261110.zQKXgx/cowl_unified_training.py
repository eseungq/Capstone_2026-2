"""Prepare and run the cowl unified GOOD/DEFECT baseline."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path

from frame_model.check import read_image
from frame_model.train import execute, manifests, subset


ROLES = ("train","model_selection","calibration_fit","policy_development")
TYPES = ["고정핀 불량","연계 불량"]
LIMITS = ["Photo-level classification of fixed-pin or linkage defects.",
          "Both-defect and both-normal joint labels are absent from the source.",
          "Calibration and policy-development pixels remain reserved during training."]
VERSIONS = {"torch":"2.10.0a0+b558c986e8.nv25.11","torchvision":"0.25.0a0+7a13ad0f",
            "timm":"1.0.30","Pillow":"12.0.0","numpy":"2.1.0"}
PIN = Path("outputs/cowl_pin_training_12e_20261109.Vj4ZcV")
LINK = Path("outputs/cowl_linkage_split_20261109.SyXrpy")


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def save(path,value):
    with path.open("x",encoding="utf-8") as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write("\n")


def jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def latest(name):
    return Path(load(Path(f"cowl_model/latest_{name}.json"))["directory"])


def prepare(stage):
    config_hashes = {str(p):sha(p/"config.json") for p in (PIN,LINK)}
    assert list(config_hashes.values()) == [
        "6a248ee543fe6faa53168e15b7bbd4c8b4ba9ba6417e459c500702e1e660686b",
        "de12f7bf0c7bbd1b58e1675990fd2e3e1523d89f74788f27400bad9db7d808a0"]
    configs = [load(p/"config.json") for p in (PIN,LINK)]
    common = ("model_name","image_size","epochs","batch_size","learning_rate","weight_decay","seed","mean","std",
              "prediction_cutoff","initialization","trainer_sha256","class_mapping","archive_stats")
    assert all(configs[0][k]==configs[1][k] for k in common)
    config = {k:configs[0][k] for k in common}
    assert (config["image_size"],config["epochs"],config["batch_size"])==(224,12,8)
    assigned = {}
    for c,kind in zip(configs,TYPES,strict=True):
        for role in ROLES:
            item = c["manifests"][role]
            path = Path(item["path"])
            assert sha(path)==item["sha256"]
            with path.open(encoding="utf-8-sig",newline="") as f:
                table = list(csv.DictReader(f))
            assert len(table)==c["roles"][role]
            for r in table:
                assert r["defect_type"]==kind and r["image_id"] not in assigned
                assigned[r["image_id"]]=(role,r)
    assert len(assigned)==20222
    audit = latest("full_similarity")
    fps_path = audit/"fingerprints.jsonl"
    relations_path = audit/"candidates.jsonl"
    manual_path = latest("similarity_import")/"future_split_constraints.json"
    fps = jsonl(fps_path)
    assert len(fps)==20386 and load(audit/"summary.json")["decode_errors"]==0
    parent = {r["image_id"]:r["image_id"] for r in fps}

    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i

    def join(a,b):
        a,b=sorted((root(a),root(b)))
        parent[b]=a

    pixels,source = defaultdict(list),defaultdict(list)
    for r in fps:
        i=r["image_id"]
        if i in assigned:
            assert assigned[i][1]["image_sha256"]==r["source_sha256"]
        pixels[r["display_sha256"]].append(i)
        source[r["source_sha256"]].append(i)
    for collection in (pixels,source):
        for members in collection.values():
            for i in members[1:]:
                join(members[0],i)
    for edge in jsonl(relations_path)+load(manual_path)["links"]:
        join(edge["a"],edge["b"])
    group_roles={}
    for i,(role,_) in assigned.items():
        if group_roles.setdefault(root(i),role)!=role:
            raise ValueError("Combined similarity component crosses assigned roles")

    removed=[]
    duplicates=[sorted(set(members)&assigned.keys()) for members in pixels.values()]
    for members in sorted(group for group in duplicates if len(group)>1):
        assert len(members)==2 and {assigned[i][0] for i in members}=={"train"}
        assert {assigned[i][1]["class_id"] for i in members}=={"0"}
        # Keep one fixed-pin duplicate and one linkage duplicate across the two pairs.
        kind=TYPES[len(removed)]
        keep=next(i for i in members if assigned[i][1]["defect_type"]==kind)
        drop,=set(members)-{keep}
        removed.append(dict(kept=keep,excluded=drop,source_label="GOOD in both photos"))
        del assigned[drop]
    assert len(removed)==2 and len(assigned)==20220
    tables=defaultdict(list)
    for ident,(role,row) in sorted(assigned.items()):
        group=hashlib.sha256(root(ident).encode()).hexdigest()[:24]
        tables[role].append(dict(row,group_id=f"cowl-{group}"))
    config.update(part_code="COWL_COVER",scope="Unified fixed pin and linkage",inspection_types=TYPES,
                  roles={role:len(tables[role]) for role in ROLES},manifests={},limitations=LIMITS)
    counts={}
    for role in ROLES:
        path=stage/f"{role}.csv"
        rows=tables[role]
        with path.open("x",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        config["manifests"][role]=dict(path=str(path),sha256=sha(path))
        counts[role]={kind:Counter(r["class_id"] for r in rows if r["defect_type"]==kind) for kind in TYPES}
    save(stage/"config.json",config)
    verified=check(stage,check_record=False)
    _,rows,_=verified
    for table in rows.values():
        for r in subset(table,1):
            assert read_image(r)[1].size==(224,224)
    save(stage/"preflight.json",dict(status="passed",config_sha256=sha(stage/"config.json"),
                                    input_check_samples=8,split_counts=counts,roles=config["roles"],
                                    excluded_exact_duplicates=removed,role_overlap=0,official_validation_used=False,
                                    source_configs=config_hashes,similarity_fingerprints_sha256=sha(fps_path),
                                    similarity_candidates_sha256=sha(relations_path),human_links_sha256=sha(manual_path)))
    print("COWL_UNIFIED_PREPARED",config["roles"],flush=True)


def check(stage,check_record=True):
    config,tables=manifests(stage)
    if check_record:
        evidence=load(stage/"preflight.json")
        assert evidence["status"]=="passed" and evidence["config_sha256"]==sha(stage/"config.json")
    assert config["roles"]==dict(train=14152,model_selection=2022,calibration_fit=2022,policy_development=2024)
    assert config["inspection_types"]==TYPES
    for name,expected in config["trainer_sha256"].items():
        assert sha(name)==expected
    initial=Path(config["initialization"]["path"])
    assert sha(initial)==config["initialization"]["sha256"]
    return config,tables,initial


def main(stage,mode):
    if mode=="prepare":
        prepare(stage)
        return
    config,tables,initial=check(stage)
    if mode=="check":
        print("COWL_UNIFIED_PREFLIGHT_OK",flush=True)
        return
    assert {k:importlib.metadata.version(k) for k in VERSIONS}==VERSIONS
    smoke=mode=="smoke"
    if smoke:
        tables={role:subset(rows,16 if role=="train" else 8) for role,rows in tables.items()}
        assert {role:len(rows) for role,rows in tables.items()}=={"train":64,"model_selection":32}
    else:
        evidence=stage/"runs/smoke"
        status=load(evidence/"status.json")
        trial=load(evidence/"run_config.json")
        assert status["status"]=="passed" and status["mode"]=="smoke" and not status["quality_evaluation"]
        assert trial["versions"]==VERSIONS and trial["experiment_context"]["frozenConfigSHA256"]==sha(stage/"config.json")
    out=stage/"runs"/mode
    out.mkdir()
    execute(config,tables,stage,out,smoke,initial_state=initial,
            context=dict(partCode="COWL_COVER",inspectionScope="UNIFIED_FIXED_PIN_LINKAGE",
                         frozenConfigSHA256=sha(stage/"config.json"),qualityEvaluation=not smoke))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","check","smoke","train"))
    parser.add_argument("stage",type=Path)
    args=parser.parse_args()
    main(args.stage.resolve(strict=True),args.mode)
