"""Shared Housing library. Run behind HTTPS; all persistent state is in DATA_DIR."""
import getpass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
import zipfile
from functools import wraps
from contextlib import closing

from flask import Flask, g, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

MAX_FILE = 30 * 1024 * 1024
FIELDS = ('length', 'width', 'stepHeight', 'stepLength')


def create_app(data_dir=None, seed=True):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE + 128 * 1024
    folder = Path(data_dir or os.environ.get('DATA_DIR', './data')).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    dbpath = folder / 'housing.sqlite3'
    origins = set(os.environ.get('ALLOWED_ORIGINS', 'https://yhao68142-maker.github.io,http://127.0.0.1:8765').split(','))

    def connect():
        c = sqlite3.connect(dbpath, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    with closing(connect()) as c, c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE NOT NULL,
          password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','editor')), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS parts(id TEXT PRIMARY KEY, part TEXT NOT NULL COLLATE NOCASE,
          version TEXT NOT NULL COLLATE NOCASE, data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
          deleted INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL, updated_by TEXT,
          filename TEXT, file BLOB, sha256 TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS part_version ON parts(part,version) WHERE deleted=0;
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL, actor TEXT, action TEXT, target TEXT);
        CREATE TABLE IF NOT EXISTS attempts(at REAL, username TEXT, ip TEXT);
        CREATE INDEX IF NOT EXISTS attempts_time ON attempts(at);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        ''')
        c.execute('BEGIN IMMEDIATE')
        if seed and not c.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
            rows = json.loads(Path(__file__).with_name('seed.json').read_text(encoding='utf-8'))
            for r in rows:
                rid = 'legacy-' + str(r['sourceRow'])
                # Source rows can share a part name. Distinguish legacy records explicitly.
                r.update(id=rid, name=r['part'], version='原表-' + str(r['sourceRow']), notes='', source='内置 Excel')
                c.execute('INSERT INTO parts(id,part,version,data,updated) VALUES(?,?,?,?,?)',
                          (rid, r['part'], r['version'], json.dumps(r, ensure_ascii=False), time.time()))
            c.execute("INSERT INTO meta VALUES('seeded','1')")

    def db():
        if 'db' not in g:
            g.db = connect()
        return g.db

    @app.teardown_appcontext
    def close(_error):
        if 'db' in g:
            g.db.close()

    @app.before_request
    def origin_check():
        origin = request.headers.get('Origin')
        if origin and origin not in origins:
            return jsonify(error='此网页地址未获准访问后台'), 403
        if request.method == 'OPTIONS':
            return '', 204

    @app.after_request
    def headers(response):
        origin = request.headers.get('Origin')
        if origin in origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error='请求过大，3D 文件上限为 30 MB' if error.code == 413 else error.description), error.code

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(sqlite3.IntegrityError)
    def duplicate(_error):
        db().rollback()
        return jsonify(error='同一零件编号和版本已存在，或用户名已被使用'), 409

    def authorized(admin=False):
        def decorate(fn):
            @wraps(fn)
            def wrap(*args, **kwargs):
                token = request.headers.get('Authorization', '').removeprefix('Bearer ')
                user = db().execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id '
                                    'WHERE s.token=? AND s.expires>? AND u.active=1',
                                    (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
                if not user:
                    return jsonify(error='请使用已授权的账号登录'), 401
                if admin and user['role'] != 'admin':
                    return jsonify(error='只有管理员可以管理账号和完整备份'), 403
                g.user = user
                return fn(*args, **kwargs)
            return wrap
        return decorate

    def audit(action, target):
        db().execute('INSERT INTO audit(at,actor,action,target) VALUES(?,?,?,?)',
                     (time.time(), g.user['username'], action, target))

    def password_hash(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ValueError('密码须为 12–128 个字符')
        return generate_password_hash(password, method='pbkdf2:sha256:600000')

    def json_body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ValueError('请求必须是 JSON 对象')
        return value

    @app.get('/api/health')
    def health():
        return jsonify(ok=True, version='2.0')

    @app.post('/api/login')
    def login():
        data = json_body()
        username, password = str(data.get('username', '')).strip().lower(), data.get('password', '')
        now, ip = time.time(), request.remote_addr
        db().execute('DELETE FROM attempts WHERE at<?', (now-900,))
        count = db().execute('SELECT count(*) FROM attempts WHERE username=? OR ip=?', (username, ip)).fetchone()[0]
        if count >= 20:
            db().commit()
            return jsonify(error='登录尝试过多，请 15 分钟后重试'), 429
        db().execute('INSERT INTO attempts VALUES(?,?,?)', (now, username, ip))
        db().commit()
        user = db().execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
        # Equal-cost verification for unknown accounts; never expose which username exists.
        candidate = user['password'] if user else app.config['DUMMY_HASH']
        valid = isinstance(password, str) and len(password) <= 128 and check_password_hash(candidate, password)
        if not user or not valid:
            return jsonify(error='用户名或密码错误，或账号已停用'), 401
        token = secrets.token_urlsafe(48)
        db().execute('DELETE FROM sessions WHERE expires<?', (now,))
        db().execute('DELETE FROM attempts WHERE username=?', (username,))
        db().execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], now+8*3600))
        db().commit()
        return jsonify(token=token, username=user['username'], role=user['role'])

    @app.post('/api/logout')
    @authorized()
    def logout():
        token = request.headers['Authorization'].removeprefix('Bearer ')
        db().execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))
        db().commit()
        return jsonify(ok=True)

    def record(row):
        item = json.loads(row['data'])
        item.update(id=row['id'], revision=row['revision'], deleted=bool(row['deleted']),
                    updated=row['updated'], filename=row['filename'], sha256=row['sha256'])
        return item

    columns = 'id,data,revision,deleted,updated,filename,sha256'

    @app.get('/api/parts')
    def parts():
        return jsonify(records=[record(r) for r in db().execute(f'SELECT {columns} FROM parts WHERE deleted=0 ORDER BY updated DESC')])

    @app.get('/api/trash')
    @authorized()
    def trash():
        return jsonify(records=[record(r) for r in db().execute(f'SELECT {columns} FROM parts WHERE deleted=1 ORDER BY updated DESC')])

    def metadata(data):
        if not isinstance(data, dict):
            raise ValueError('产品信息必须是对象')
        out = {}
        for key, maximum in [('part', 160), ('name', 200), ('model', 200), ('version', 80), ('notes', 4000)]:
            value = data.get(key, '')
            if not isinstance(value, str) or len(value) > maximum:
                raise ValueError('产品文本过长或格式错误')
            out[key] = value.strip()
        if not out['part'] or not out['name'] or not out['version']:
            raise ValueError('零件编号、名称和版本必填')
        for key in FIELDS:
            value = data.get(key)
            if value is None and key.startswith('step'):
                out[key] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e6:
                raise ValueError('尺寸须为有效数字，未知台阶尺寸应留空')
            if (key in ('length', 'width') and value <= 0) or (key == 'stepLength' and value < 0):
                raise ValueError('长宽须大于零，台阶长度不能为负')
            out[key] = value
        out.update(warnings=[], raw=json.dumps(out, ensure_ascii=False), source='共享零件库', sourceRow=0)
        return out

    def file_data(required):
        f = request.files.get('file')
        if not f or not f.filename:
            if required:
                raise ValueError('新增零件需要保存原始 3D 文件')
            return None
        name = f.filename.replace('\\', '/').split('/')[-1]
        if len(name) > 240 or any(ord(c) < 32 for c in name) or Path(name).suffix.lower() not in ('.step','.stp','.stl','.sldprt'):
            raise ValueError('请选择 STEP、STL 或 SLDPRT 文件')
        body = f.read(MAX_FILE+1)
        if not body or len(body) > MAX_FILE:
            raise ValueError('文件须非空且不超过 30 MB')
        return name, body, hashlib.sha256(body).hexdigest()

    @app.post('/api/parts')
    @authorized()
    def create():
        item = metadata(json.loads(request.form.get('metadata', '{}')))
        name, body, digest = file_data(True)
        rid = str(uuid.uuid4())
        with db():
            db().execute('INSERT INTO parts(id,part,version,data,updated,updated_by,filename,file,sha256) VALUES(?,?,?,?,?,?,?,?,?)',
                         (rid,item['part'],item['version'],json.dumps(item,ensure_ascii=False),time.time(),g.user['username'],name,body,digest))
            audit('create', rid)
        return jsonify(id=rid), 201

    @app.put('/api/parts/<rid>')
    @authorized()
    def update(rid):
        incoming = json.loads(request.form.get('metadata', '{}'))
        item, file = metadata(incoming), file_data(False)
        with db():
            row = db().execute('SELECT data FROM parts WHERE id=?', (rid,)).fetchone()
            if row:
                old = json.loads(row['data'])
                for key in ('sourceRow', 'source', 'warnings', 'raw'):
                    item[key] = old.get(key, item[key])
            values = [item['part'],item['version'],json.dumps(item,ensure_ascii=False),time.time(),g.user['username']]
            sql = 'UPDATE parts SET part=?,version=?,data=?,updated=?,updated_by=?,revision=revision+1'
            if file:
                sql += ',filename=?,file=?,sha256=?'
                values.extend(file)
            sql += ' WHERE id=? AND revision=? AND deleted=0'
            values.extend([rid,incoming.get('revision')])
            if db().execute(sql, values).rowcount != 1:
                return jsonify(error='记录已被其他用户修改或删除，请刷新后重新编辑'), 409
            audit('update', rid)
        return jsonify(ok=True)

    @app.post('/api/parts/<rid>/<action>')
    @authorized()
    def change_state(rid, action):
        if action not in ('delete', 'restore'):
            return jsonify(error='操作不存在'), 404
        value = int(action == 'delete')
        with db():
            changed = db().execute('UPDATE parts SET deleted=?,revision=revision+1,updated=?,updated_by=? WHERE id=? AND revision=? AND deleted=?',
                                   (value,time.time(),g.user['username'],rid,json_body().get('revision'),1-value)).rowcount
            if changed != 1:
                return jsonify(error='记录已变化，请刷新后重试'), 409
            audit(action, rid)
        return jsonify(ok=True)

    @app.get('/api/parts/<rid>/file')
    @authorized()
    def download(rid):
        row = db().execute('SELECT filename,file FROM parts WHERE id=?', (rid,)).fetchone()
        if not row or not row['filename']:
            return jsonify(error='此记录没有原始 3D 文件'), 404
        return send_file(io.BytesIO(row['file']), as_attachment=True, download_name=row['filename'], mimetype='application/octet-stream')

    @app.get('/api/users')
    @authorized(admin=True)
    def users():
        return jsonify(users=[dict(r) for r in db().execute('SELECT id,username,role,active FROM users ORDER BY username')])

    @app.post('/api/users')
    @authorized(admin=True)
    def create_user():
        data = json_body()
        username = str(data.get('username', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username):
            raise ValueError('用户名须为 3–40 位字母、数字、点、横线或下划线')
        hashed = password_hash(data.get('password'))
        with db():
            db().execute('INSERT INTO users VALUES(?,?,?,?,1)', (str(uuid.uuid4()),username,hashed,'editor'))
            audit('create-user',username)
        return jsonify(ok=True),201

    @app.put('/api/users/<uid>')
    @authorized(admin=True)
    def update_user(uid):
        if uid == g.user['id']:
            return jsonify(error='请通过服务器管理命令修改管理员账号'),400
        data = json_body()
        with db():
            row = db().execute('SELECT * FROM users WHERE id=? AND role=?',(uid,'editor')).fetchone()
            if not row:
                return jsonify(error='账号不存在'),404
            if 'active' in data:
                if type(data['active']) is not bool:
                    raise ValueError('账号状态必须是布尔值')
                db().execute('UPDATE users SET active=? WHERE id=?',(int(data['active']),uid))
            if data.get('password'):
                db().execute('UPDATE users SET password=? WHERE id=?',(password_hash(data['password']),uid))
            db().execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            audit('update-user',uid)
        return jsonify(ok=True)

    @app.get('/api/backup')
    @authorized(admin=True)
    def backup():
        # One read snapshot: metadata and original binaries match each other.
        output = io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            db().execute('BEGIN')
            all_records = []
            for row in db().execute('SELECT * FROM parts ORDER BY id'):
                item = record(row)
                item['backupFile'] = 'files/'+row['id']+'/'+row['filename'] if row['filename'] else None
                all_records.append(item)
                if item['backupFile']:
                    z.writestr(item['backupFile'],row['file'])
            z.writestr('records.json',json.dumps({'schemaVersion':1,'records':all_records},ensure_ascii=False,indent=2))
            z.writestr('audit.json',json.dumps([dict(r) for r in db().execute('SELECT * FROM audit')],ensure_ascii=False))
            db().rollback()
        output.seek(0)
        return send_file(output,as_attachment=True,download_name='housing-backup.zip',mimetype='application/zip')

    app.config['DUMMY_HASH'] = generate_password_hash(secrets.token_urlsafe(24),method='pbkdf2:sha256:600000')
    app.config['DB_PATH'] = str(dbpath)
    return app


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','admin'])
    parser.add_argument('--username',default='admin')
    parser.add_argument('--port',type=int,default=8787)
    args = parser.parse_args()
    app = create_app()
    if args.command == 'admin':
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}',args.username):
            raise SystemExit('Invalid username')
        password = getpass.getpass('New admin password (12-128 characters): ')
        if not 12 <= len(password) <= 128 or password != getpass.getpass('Confirm password: '):
            raise SystemExit('Invalid password or mismatch')
        with closing(sqlite3.connect(app.config['DB_PATH'])) as c, c:
            username = args.username.lower()
            row = c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
            uid = row[0] if row else str(uuid.uuid4())
            c.execute('INSERT INTO users VALUES(?,?,?,?,1) ON CONFLICT(username) DO UPDATE SET password=excluded.password,role=excluded.role,active=1',
                      (uid,username,generate_password_hash(password,method='pbkdf2:sha256:600000'),'admin'))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        print('Administrator ready. Password not stored in source code.')
    else:
        app.run(host='127.0.0.1',port=args.port,debug=False)
