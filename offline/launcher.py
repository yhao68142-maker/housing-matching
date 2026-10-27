"""Offline-only desktop file picker and loopback web host. No network upload."""
import json
import mimetypes
from pathlib import Path
import queue
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

MAX_FILE = 30 * 1024 * 1024
ASSETS = {'index.html','style.css','housing-data.js','matcher.js','step-features.js',
          'app.js','cloud-config.js','library.js','offline.js','cad-worker.js','README.md',
          'vendor/occt-import-js.js','vendor/occt-import-js.wasm','vendor/LICENSE.md'}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root):
        self.root = Path(root)
        self.token = secrets.token_urlsafe(32)
        self.selection = None
        self.lock = threading.Lock()
        self.picks = queue.Queue(maxsize=1)
        super().__init__(('127.0.0.1', 0), Handler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
        self.prefix = '/' + self.token + '/'
        self.url = self.origin + self.prefix

    def select(self, path):
        path = Path(path)
        if path.suffix.lower() not in ('.step','.stp','.stl'):
            raise ValueError('请选择 STEP、STP 或 STL；SLDPRT 请先另存为 STEP。')
        with path.open('rb') as f:
            body = f.read(MAX_FILE+1)
        if not body or len(body) > MAX_FILE:
            raise ValueError('请选择非空且不超过 30 MB 的文件。')
        with self.lock:
            self.selection = (secrets.token_hex(16), path.name, body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Do not log local session URLs or filesystem names.

    def reply(self, code, body=b'', content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        s = self.server
        path = urlsplit(self.path).path
        if self.headers.get('Host') != urlsplit(s.origin).netloc:
            self.reply(403); return None
        if self.headers.get('Origin') not in (None,s.origin) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.reply(403); return None
        if not path.startswith(s.prefix):
            self.reply(404); return None
        return path[len(s.prefix):]

    def do_GET(self):
        path = self.route()
        if path is None: return
        s = self.server
        if path == 'cloud-config.js':
            self.reply(200,b"window.HOUSING_API_URL='';window.HOUSING_OFFLINE=true;",'application/javascript');return
        if path == 'native/status':
            with s.lock:
                item = s.selection
            self.reply(200,json.dumps({'id':item[0],'name':item[1]} if item else {},ensure_ascii=False).encode());return
        if path.startswith('native/model/'):
            with s.lock:
                item = s.selection
            if not item or path != 'native/model/'+item[0]: self.reply(404);return
            self.reply(200,item[2],'application/octet-stream');return
        path = path or 'index.html'
        if path not in ASSETS: self.reply(404);return
        try:
            body = (s.root/path).read_bytes()
        except OSError:
            self.reply(404);return
        kind = 'application/wasm' if path.endswith('.wasm') else 'application/javascript' if path.endswith('.js') else mimetypes.guess_type(path)[0] or 'application/octet-stream'
        self.reply(200,body,kind)

    def do_POST(self):
        path = self.route()
        if path is None: return
        if path != 'native/pick': self.reply(404);return
        if self.headers.get('Origin') != self.server.origin or self.headers.get('X-Housing-Local') != self.server.token:
            self.reply(403);return
        if not self.server.picks.full(): self.server.picks.put_nowait(True)
        self.reply(202,b'{}')


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root_path = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'site'
    if not root_path.exists(): root_path = Path(__file__).resolve().parent.parent/'dist'
    root = tk.Tk()
    root.title('Housing 离线工作台')
    root.geometry('540x300')
    root.minsize(500,280)
    if not (root_path/'vendor/occt-import-js.wasm').exists():
        messagebox.showerror('缺少文件','请完整解压离线包，保留 _internal 文件夹。',parent=root);root.destroy();return
    server = LocalServer(root_path)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    frame = ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Housing 离线工作台',font=('Microsoft YaHei',18,'bold')).pack(anchor='w')
    ttk.Label(frame,text='无需联网 · 通过本地窗口选择零件 · 文件不上传',wraplength=480).pack(anchor='w',pady=12)
    status = tk.StringVar(value='请保持此窗口打开；关闭后离线网页将停止服务。')

    def pick():
        root.lift()
        path = filedialog.askopenfilename(parent=root,title='选择需要测量的零件',filetypes=[('3D 零件','*.step *.stp *.stl'),('所有文件','*.*')])
        if not path: return
        try:
            server.select(path)
            status.set('已选择：'+Path(path).name+'。请在网页中查看测量结果。')
        except (OSError,ValueError) as e:
            messagebox.showerror('无法读取零件',str(e),parent=root)

    ttk.Button(frame,text='选择零件并测量',command=pick).pack(fill='x',pady=5)
    ttk.Button(frame,text='打开 / 返回离线网页',command=lambda:webbrowser.open(server.url)).pack(fill='x',pady=5)
    ttk.Label(frame,textvariable=status,wraplength=480).pack(anchor='w',pady=12)

    def tick():
        try: server.picks.get_nowait()
        except queue.Empty: pass
        else: pick()
        root.after(250,tick)

    def close():
        server.shutdown();server.server_close();root.destroy()

    root.protocol('WM_DELETE_WINDOW',close)
    root.after(250,tick)
    root.after(400,lambda:webbrowser.open(server.url))
    root.mainloop()


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        import http.client
        import tkinter as tk
        widget=tk.Tk();widget.withdraw();widget.update();widget.destroy()
        root_path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'site'
        if not root_path.exists():root_path=Path(__file__).resolve().parent.parent/'dist'
        assert (root_path/'vendor/occt-import-js.wasm').stat().st_size>1000
        server=LocalServer(root_path)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            for asset in ('','cloud-config.js','offline.js','vendor/occt-import-js.wasm'):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                connection.request('GET',server.prefix+asset)
                response=connection.getresponse()
                assert response.status==200 and response.read()
                connection.close()
        finally:server.shutdown();server.server_close()
    else:
        main()
