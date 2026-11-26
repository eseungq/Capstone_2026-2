"""Safety tests for local management; no real Docker or sockets."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_api.manage_dev import read_session,require_owned,preflight

class DevManagementTests(unittest.TestCase):
    def test_stop_identity_requires_exact_cid_image_and_mount(self):
        cid='a'*64;project=Path('/fixture/project');info={'Id':cid,'Name':'/door-ai-api-serve','Config':{'Image':'nvcr.io/nvidia/pytorch:25.11-py3'},'Mounts':[{'Source':str(project),'Destination':str(project)}]}
        require_owned(info,cid,project)
        with self.assertRaises(ValueError):require_owned(info,'b'*64,project)
        with self.assertRaises(ValueError):require_owned(dict(info,Name='/prototype'),cid,project)
        with self.assertRaises(ValueError):require_owned(dict(info,Mounts=[]),cid,project)
    def test_record_rejects_unowned_or_malformed_cid_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);cidfile=folder/'serve_fixture.cid';cidfile.write_text('a'*64);session=folder/'session.json'
            data={'scope':'owned-development-serve-launch','cidfile':str(cidfile),'modelVersion':'fixture'};session.write_text(json.dumps(data))
            self.assertEqual(read_session(session,folder)[1],'a'*64)
            cidfile.write_text('door-ai-api-serve')
            with self.assertRaises(ValueError):read_session(session,folder)
            data['cidfile']=str(folder/'prototype.cid');session.write_text(json.dumps(data))
            with self.assertRaises(ValueError):read_session(session,folder)
    def test_missing_image_origin_is_not_silently_replaced(self):
        env={'DOOR_API_MODEL_VERSION':'UNREGISTERED-fixture','DOOR_API_DEVELOPMENT_CONTRACT':'1'}
        with patch.dict(os.environ,env,clear=True):
            with self.assertRaisesRegex(ValueError,'IMAGE_ORIGIN'):preflight()
        env['DOOR_API_IMAGE_ORIGIN']='http://fixture:8080'
        with patch.dict(os.environ,env,clear=True):preflight()
        env['DOOR_API_IMAGE_ORIGIN']='http://user:secret@fixture'
        with patch.dict(os.environ,env,clear=True):
            with self.assertRaises(ValueError):preflight()

if __name__=='__main__':unittest.main()
