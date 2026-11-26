"""Execute launcher branches with a fake Docker/Python in a temporary tree, NEVER GPU."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class LauncherTests(unittest.TestCase):
    def fixture_run(self,mode,extra_env=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);project=folder/'project';project.mkdir();binpath=folder/'bin';binpath.mkdir();capture=folder/'capture.json'
            script=(ROOT/'ai_api/run_gpu.sh').read_text().replace('project=/path/to/private/validated-project','project='+str(project)).replace('training=/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009','training='+str(folder/'training'))
            launcher=folder/'run.sh';launcher.write_text(script)
            docker=binpath/'docker';docker.write_text('''#!/usr/bin/env python3
import os,sys,subprocess
if sys.argv[1:3]==['image','inspect']:sys.exit(0)
if sys.argv[1]!='run':sys.exit(9)
env=os.environ.copy()
for i,arg in enumerate(sys.argv):
 if arg=='-e':
  key,value=sys.argv[i+1].split('=',1);env[key]=value
result=subprocess.run(['bash','-se'],input=sys.stdin.buffer.read(),env=env)
sys.exit(result.returncode)
''');docker.chmod(0o755)
            python=binpath/'python';python.write_text('''#!/usr/bin/env python3
import json,os,sys
if '-m' in sys.argv and any(x in sys.argv for x in ['ai_api.verify_integration','ai_api.verify_backend_profile','ai_api.server']):
 with open(os.environ['LAUNCH_TEST_CAPTURE'],'w') as f:json.dump({'argv':sys.argv[1:],'mode':os.environ.get('DOOR_API_MODE'),'fixtureOnly':True},f)
elif '-' in sys.argv:sys.stdin.read()
''');python.chmod(0o755)
            env=os.environ.copy();env.update(PATH=str(binpath)+os.pathsep+env['PATH'],DOOR_API_MODEL_VERSION='LAUNCH_FIXTURE_ONLY',DOOR_API_DEVELOPMENT_CONTRACT='1',LAUNCH_TEST_CAPTURE=str(capture))
            for key in ['DOOR_DOCKER_SUDO','DOOR_API_ROI_FILE','DOOR_API_IMAGE_ORIGIN','DOOR_API_RESPONSE_PROFILE','DOOR_API_SESSION_RECORD','DOOR_API_CAM_FORMAT','DOOR_API_JPEG_QUALITY']:env.pop(key,None)
            env.update(extra_env or {})
            result=subprocess.run(['bash',str(launcher),mode],env=env,capture_output=True,text=True,timeout=20)
            return result,json.loads(capture.read_text()) if capture.exists() else None
    def test_integration_without_roi_reaches_correct_python_module(self):
        result,capture=self.fixture_run('integration');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(capture['mode'],'integration');self.assertIn('ai_api.verify_integration',capture['argv']);self.assertNotIn('ai_api.focused_cam',capture['argv'])
    def test_focused_still_requires_roi(self):
        result,capture=self.fixture_run('focused');self.assertNotEqual(result.returncode,0);self.assertIn('DOOR_API_ROI_FILE',result.stdout+result.stderr);self.assertIsNone(capture)

    def test_backend_verifier_without_roi_or_external_origin(self):
        result,capture=self.fixture_run('backend-verify');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('ai_api.verify_backend_profile',capture['argv']);self.assertNotIn('ai_api.focused_cam',capture['argv'])
    def test_serve_preserves_legacy_default_and_forwards_opt_in_profile(self):
        for profile in ['development-proposal-v4-pending','backend-v4-1028-partial']:
            env={'DOOR_API_IMAGE_ORIGIN':'http://fixture:8080'}
            if profile!='development-proposal-v4-pending':env['DOOR_API_RESPONSE_PROFILE']=profile
            result,capture=self.fixture_run('serve',env);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            args=capture['argv'];self.assertIn('ai_api.server',args);self.assertEqual(args[args.index('--response-profile')+1],profile)

    def test_backend_jpeg_parameters_forwarded(self):
        result,capture=self.fixture_run('backend-verify',{'DOOR_API_CAM_FORMAT':'jpeg','DOOR_API_JPEG_QUALITY':'90'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);args=capture['argv'];self.assertEqual(args[args.index('--cam-format')+1],'jpeg');self.assertEqual(args[args.index('--jpeg-quality')+1],'90')

if __name__=='__main__':unittest.main()
