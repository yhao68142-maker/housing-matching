import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from launcher import LocalServer


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'index.html').write_text('offline-page')
        (self.root/'secret.txt').write_text('private')
        self.server=LocalServer(self.root)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()

    def get(self,path='',headers=None,method='GET'):
        req=urllib.request.Request(self.server.url+path,headers=headers or {},method=method)
        try:
            with urllib.request.urlopen(req) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()

    def test_static_allowlist_and_disabled_cloud(self):
        self.assertEqual(self.get(),(200,b'offline-page'))
        self.assertEqual(self.get('secret.txt')[0],404)
        self.assertEqual(self.get('../secret.txt')[0],404)
        self.assertIn(b'HOUSING_OFFLINE=true',self.get('cloud-config.js')[1])
        self.assertEqual(self.get(headers={'Host':'attacker.example'})[0],403)

    def test_cross_site_requests_and_picker_require_local_session(self):
        self.assertEqual(self.get('native/status',{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.get('native/pick',method='POST')[0],403)
        self.assertEqual(self.get('native/pick',{'Origin':self.server.origin,'X-Housing-Local':self.server.token},'POST')[0],202)
        self.assertTrue(self.server.picks.get_nowait())

    def test_only_explicit_native_selection_can_be_read(self):
        self.assertEqual(json.loads(self.get('native/status')[1]),{})
        model=self.root/'零件.step';model.write_bytes(b'ISO-10303-21; sample')
        self.server.select(model)
        status=json.loads(self.get('native/status')[1])
        self.assertEqual(status['name'],'零件.step')
        self.assertNotIn(str(self.root),json.dumps(status))
        self.assertEqual(self.get('native/model/'+status['id'])[1],model.read_bytes())
        self.server.select(model)
        self.assertEqual(self.get('native/model/'+status['id'])[0],404)
        with self.assertRaises(ValueError):self.server.select(self.root/'secret.txt')
        model.write_bytes(b'')
        with self.assertRaises(ValueError):self.server.select(model)


if __name__=='__main__':unittest.main()
