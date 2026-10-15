from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
import os
import subprocess
import sys

from app import create_app
from werkzeug.security import generate_password_hash


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'test-only-password-123'
        cls.hashed = generate_password_hash(cls.password,method='pbkdf2:sha256:600000')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name,seed=False)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        with closing(sqlite3.connect(self.app.config['DB_PATH'])) as c, c:
            c.execute('INSERT INTO users VALUES(?,?,?,?,1)',('owner','owner',self.hashed,'admin'))
            c.execute('INSERT INTO users VALUES(?,?,?,?,1)',('editor','editor',self.hashed,'editor'))
        self.admin = self.login('owner')
        self.editor = self.login('editor')

    def tearDown(self):
        self.temp.cleanup()

    def login(self,user):
        r = self.client.post('/api/login',json={'username':user,'password':self.password})
        self.assertEqual(r.status_code,200)
        return {'Authorization':'Bearer '+r.json['token']}

    def create(self,part='300-test',headers=None):
        item = dict(part=part,name='Top housing',model='OSFP',version='V02',notes='<script>x</script>',length=116,width=22.58,stepHeight=3.4,stepLength=35.29)
        return self.client.post('/api/parts',headers=headers or self.editor,data={
            'metadata':json.dumps(item),'file':(io.BytesIO(b'ISO-10303-21; test fixture'),'part.STEP')})

    def test_public_read_but_no_write_download_or_account_access(self):
        self.assertEqual(self.client.get('/api/parts').status_code,200)
        self.assertEqual(self.client.post('/api/parts').status_code,401)
        rid = self.create().json['id']
        self.assertEqual(self.client.get('/api/parts/'+rid+'/file').status_code,401)
        self.assertEqual(self.client.get('/api/users',headers=self.editor).status_code,403)
        self.assertEqual(self.client.get('/api/backup',headers=self.editor).status_code,403)
        self.assertEqual(self.client.get('/api/trash').status_code,401)

    def test_crud_conflicts_trash_restore_and_atomic_original(self):
        r = self.create();self.assertEqual(r.status_code,201)
        rid = r.json['id'];row = self.client.get('/api/parts').json['records'][0]
        self.assertEqual(row['stepHeight'],3.4)
        self.assertEqual(self.create().status_code,409)
        row['name'] = 'Updated'
        url = '/api/parts/'+rid
        self.assertEqual(self.client.put(url,headers=self.editor,data={'metadata':json.dumps(row)}).status_code,200)
        self.assertEqual(self.client.put(url,headers=self.editor,data={'metadata':json.dumps(row)}).status_code,409)
        self.assertEqual(self.client.get(url+'/file',headers=self.editor).data,b'ISO-10303-21; test fixture')
        self.assertEqual(self.client.post(url+'/delete',headers=self.editor,json={'revision':2}).status_code,200)
        self.assertEqual(self.client.get('/api/parts').json['records'],[])
        trash = self.client.get('/api/trash',headers=self.editor).json['records']
        self.assertEqual(len(trash),1)
        self.assertEqual(self.client.post(url+'/restore',headers=self.editor,json={'revision':3}).status_code,200)
        self.assertEqual(len(self.client.get('/api/parts').json['records']),1)

    def test_account_authorization_and_revocation(self):
        self.assertEqual(self.client.post('/api/users',headers=self.editor,json={}).status_code,403)
        self.assertEqual(self.client.post('/api/users',headers=self.admin,json={'username':'new.user','password':self.password}).status_code,201)
        self.assertEqual(self.client.put('/api/users/editor',headers=self.admin,json={'active':False}).status_code,200)
        self.assertEqual(self.client.get('/api/trash',headers=self.editor).status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'username':'editor','password':self.password}).status_code,401)

    def test_validation_and_backup_contains_files_without_passwords(self):
        self.assertEqual(self.client.post('/api/parts',headers=self.editor,data={'metadata':'{}'}).status_code,400)
        self.create()
        backup = self.client.get('/api/backup',headers=self.admin)
        self.assertEqual(backup.status_code,200)
        with zipfile.ZipFile(io.BytesIO(backup.data)) as z:
            data=json.loads(z.read('records.json'))
            self.assertEqual(z.read(data['records'][0]['backupFile']),b'ISO-10303-21; test fixture')
            self.assertNotIn('password',z.read('records.json').decode())
        # Persistent state survives a new application instance.
        second=create_app(self.temp.name,seed=False).test_client()
        self.assertEqual(len(second.get('/api/parts').json['records']),1)

    def test_origin_logout_and_file_validation(self):
        self.assertEqual(self.client.get('/api/parts',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.options('/api/parts',headers={'Origin':'https://yhao68142-maker.github.io'}).status_code,204)
        self.assertEqual(self.client.post('/api/logout',headers=self.editor).status_code,200)
        self.assertEqual(self.client.get('/api/trash',headers=self.editor).status_code,401)

    def test_legacy_seed_is_idempotent(self):
        seeded=create_app(self.temp.name,seed=True)
        count=len(seeded.test_client().get('/api/parts').json['records'])
        self.assertEqual(count,141)
        again=create_app(self.temp.name,seed=True)
        self.assertEqual(len(again.test_client().get('/api/parts').json['records']),count)

    def test_replacement_and_invalid_dimensions_do_not_corrupt_file(self):
        rid=self.create().json['id']
        row=self.client.get('/api/parts').json['records'][0]
        url='/api/parts/'+rid
        row['width']=-1
        self.assertEqual(self.client.put(url,headers=self.editor,data={'metadata':json.dumps(row),'file':(io.BytesIO(b'replacement'),'new.step')}).status_code,400)
        self.assertEqual(self.client.get(url+'/file',headers=self.editor).data,b'ISO-10303-21; test fixture')
        row['width']=22.58
        self.assertEqual(self.client.put(url,headers=self.editor,data={'metadata':json.dumps(row),'file':(io.BytesIO(b'new'),'new.exe')}).status_code,400)
        self.assertEqual(self.client.put(url,headers=self.editor,data={'metadata':json.dumps(row),'file':(io.BytesIO(b'valid replacement'),'new.step')}).status_code,200)
        self.assertEqual(self.client.get(url+'/file',headers=self.editor).data,b'valid replacement')

    def test_password_reset_and_expired_session(self):
        self.assertEqual(self.client.put('/api/users/editor',headers=self.admin,json={'password':'replacement-password-456'}).status_code,200)
        self.assertEqual(self.client.get('/api/trash',headers=self.editor).status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'username':'editor','password':self.password}).status_code,401)
        with closing(sqlite3.connect(self.app.config['DB_PATH'])) as c,c:
            c.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.client.get('/api/users',headers=self.admin).status_code,401)

    def test_disaster_backup_restore(self):
        self.create()
        snapshot=Path(self.temp.name)/'snapshot.sqlite3'
        env={**os.environ,'DATA_DIR':self.temp.name}
        subprocess.run([sys.executable,'maintenance.py','backup',str(snapshot)],env=env,check=True,capture_output=True)
        restored=Path(self.temp.name)/'restored'
        subprocess.run([sys.executable,'maintenance.py','restore',str(snapshot)],env={**env,'DATA_DIR':str(restored)},check=True,capture_output=True)
        second=create_app(restored,seed=False).test_client()
        row=second.get('/api/parts').json['records'][0]
        self.assertEqual(row['part'],'300-test')
        self.assertEqual(second.get('/api/trash',headers=self.editor).status_code,401)
        token=second.post('/api/login',json={'username':'editor','password':self.password}).json['token']
        self.assertEqual(second.get('/api/parts/'+row['id']+'/file',headers={'Authorization':'Bearer '+token}).data,b'ISO-10303-21; test fixture')


if __name__ == '__main__':
    unittest.main()
