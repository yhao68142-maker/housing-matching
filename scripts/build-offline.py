"""Run after npm run build on Windows; packages all offline dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'offline'))
from launcher import ASSETS
site=root/'offline-work/site'
site.mkdir(parents=True,exist_ok=True)
for name in ASSETS:
    source=root/'dist'/name
    target=site/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir',('--console' if '--console' in sys.argv else '--windowed'),
                '--name','Housing-Offline','--distpath',str(root/'offline-build'),
                '--workpath',str(root/'offline-work'),'--specpath',str(root/'offline-work'),
                '--add-data',str(site)+':site',str(root/'offline/launcher.py')],check=True,cwd=root)
shutil.copyfile(root/'offline/README.txt',root/'offline-build/Housing-Offline/使用说明.txt')
shutil.make_archive(str(root/'Housing-Offline-Windows'),'zip',root/'offline-build','Housing-Offline')
print('Created Housing-Offline-Windows.zip')
