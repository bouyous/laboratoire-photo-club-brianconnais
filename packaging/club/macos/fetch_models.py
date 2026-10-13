"""Fetch the exact permissively licensed weights listed in the club manifest."""
from pathlib import Path
import hashlib,json,urllib.request,zipfile,shutil,sys
root=Path(__file__).resolve().parents[3]
dest=Path(sys.argv[1]).resolve();dest.mkdir(parents=True,exist_ok=True)
for item in json.loads((root/'packaging/club/models-manifest.json').read_text()):
 target=dest/item['file']
 if target.exists() and hashlib.file_digest(target.open('rb'),'sha256').hexdigest()==item['sha256']:continue
 partial=target.with_suffix(target.suffix+'.part')
 if item['archiveMember']:
  archive=dest/'nafnet.dtmodel'
  urllib.request.urlretrieve(item['source'],archive)
  with zipfile.ZipFile(archive) as z, z.open(item['archiveMember']) as source, partial.open('wb') as out:
   shutil.copyfileobj(source,out)
  archive.unlink()
 else:urllib.request.urlretrieve(item['source'],partial)
 if partial.stat().st_size!=item['bytes'] or hashlib.file_digest(partial.open('rb'),'sha256').hexdigest()!=item['sha256']:
  raise ValueError('Model checksum mismatch: '+item['file'])
 partial.replace(target);print('Verified',item['file'],flush=True)
shutil.copy2(root/'packaging/club/models-manifest.json',dest/'manifest.json')
