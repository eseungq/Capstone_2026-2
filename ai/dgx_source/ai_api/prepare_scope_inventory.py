"""Link existing human observations to candidate representatives; no automatic culling."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from ai_api.duplicate_groups import read_csv, dump

ROOT=Path(__file__).resolve().parents[1]
CAPTURE=ROOT/'ai_api/verification/capture_selection_20261017T172736_078787Z/group_linked_proposals.json'
BOUNDARY=ROOT/'ai_api/verification/capture_audit_20261017T172917_949346Z/user_boundary_review.json'


def main():
    latest=json.loads((ROOT/'ai_api/verification/latest_data_proposal.json').read_text())
    manifest=ROOT/latest['representativeDirectory']/'candidate_manifest.csv'
    rows=read_csv(manifest)
    capture=json.loads(CAPTURE.read_text());boundary=json.loads(BOUNDARY.read_text())
    sources=[manifest,CAPTURE,BOUNDARY]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    by_path={};by_group={}
    for r in capture:
        item=dict(status=r['selectionProposal'],source=str(CAPTURE),notes=r['observation']['notes'],
                  originalOnlyVisibility=r['originalOnlyVisibility'])
        by_path[r['reviewImage']]=item;by_group[r['groupId']]=item
    for r in boundary['records']:
        item=dict(status='BOUNDARY_CHECK_PENDING',source=str(BOUNDARY),notes=r['userObservation'],originalOnlyVisibility=False)
        by_path[r['imagePath']]=item;by_group[r['groupId']]=item
    inventory=[]
    for r in rows:
        item=by_path.get(r['image_path'])
        if item is None:
            item=dict(status='OTHER_MEMBER_REVIEWED' if r['group_id'] in by_group else 'NEEDS_CAPTURE_REVIEW',
                      source=by_group[r['group_id']]['source'] if r['group_id'] in by_group else '',
                      notes='Observation exists for another group member; do not propagate framing automatically' if r['group_id'] in by_group else '',originalOnlyVisibility=False)
        inventory.append(dict(**r,capture_selection_proposal=item['status'],capture_review_source=item['source'],
                              capture_notes=item['notes'],original_only_visibility=item['originalOnlyVisibility'],
                              outer_boundary_verified=False,scope_rules_version='door-outer-scope-proposal-v1'))
    assert len(inventory)==len(rows) and len({r['group_id'] for r in inventory})==len(rows)
    assert all(not r['future_split'] for r in inventory)
    output=ROOT/'ai_api/verification'/('scope_inventory_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    with (output/'capture_inventory.csv').open('w',newline='',encoding='utf-8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
    dump(output/'reviewed_rows.json',[r for r in inventory if r['capture_selection_proposal']!='NEEDS_CAPTURE_REVIEW'])
    dump(output/'summary.json',dict(status='inventory_only',images=len(rows),counts=dict(Counter(r['capture_selection_proposal'] for r in inventory)),
          sourceHashes=hashes,scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          scopeBoundaryStatus='proposal_not_approved',originalsModified=False,trainingStarted=False,finalTestUsed=False,
          limitations='Prior six primary capture candidates have not been rechecked against the new explicit boundary proposal; no whole-door suitability certification'))
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in sources)
    print(output);print(Counter(r['capture_selection_proposal'] for r in inventory))


if __name__=='__main__':main()
