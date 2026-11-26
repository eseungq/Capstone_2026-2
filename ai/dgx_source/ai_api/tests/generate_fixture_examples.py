"""Explicit fixture artifacts only: these are not real-model response examples."""
import json
from pathlib import Path
from ai_api.tests.test_api import API, memory_request


def main():
    folder=Path(__file__).resolve().parents[1]/'examples-fixture-only'
    folder.mkdir(exist_ok=True)
    test=API();test.setUp()
    records=[]
    try:
        for name,kind,mode in [('good','good','normal'),('defect','defect','normal'),
                               ('cam_failure','defect','cam-fail'),('zero_map','defect','zero'),
                               ('constant_map','defect','constant'),('classification_error','good','inference-fail'),
                               ('damaged_image','broken','normal'),('image_access_error','missing','normal')]:
            test.engine.mode=mode
            status,body=memory_request(test.service,test.body(kind,'FIXTURE-'+name))
            artifact=dict(source='TEST FIXTURE, in-memory HTTP handler, NOT GPU or live network',
                          actualGpu=False,liveHttp=False,status=status,response=body)
            (folder/f'{name}.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
            records.append(dict(file=f'{name}.json',httpStatus=status))
        (folder/'manifest.json').write_text(json.dumps(dict(actualGpu=False,liveHttp=False,examples=records),indent=2)+'\n')
    finally:test.tearDown()
    print('Fixture-only examples:',folder)


if __name__=='__main__':main()
