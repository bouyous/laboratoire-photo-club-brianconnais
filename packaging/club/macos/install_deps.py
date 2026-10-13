"""Install native Mac dependencies, keeping Intel binaries compatible with macOS 13."""
from pathlib import Path
import json,urllib.request,hashlib,subprocess,sys
root=Path(__file__).resolve().parents[3];arch=sys.argv[1]
if arch not in ('arm64','x86_64'):raise ValueError('Unsupported Mac architecture')
wheels=root/'dist/wheels';wheels.mkdir(parents=True,exist_ok=True)
if arch=='x86_64':
 data=json.load(urllib.request.urlopen('https://pypi.org/pypi/numpy/2.2.6/json'))
 item=next(x for x in data['urls'] if x['filename']=='numpy-2.2.6-cp312-cp312-macosx_10_13_x86_64.whl')
 file=wheels/item['filename'];urllib.request.urlretrieve(item['url'],file)
 assert hashlib.file_digest(file.open('rb'),'sha256').hexdigest()==item['digests']['sha256']
 subprocess.run([sys.executable,'-m','pip','install',str(file)],check=True)
req=wheels/'requirements.txt'
req.write_text('\n'.join(line for line in (root/f'ai/requirements-macos-{arch}.txt').read_text().splitlines() if not line.startswith('opencv-python-headless'))+'\n')
subprocess.run([sys.executable,'-m','pip','install','-r',str(req)],check=True)
