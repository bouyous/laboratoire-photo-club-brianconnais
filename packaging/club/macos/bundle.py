"""Assemble an architecture-specific .app, with local AI and per-user data paths."""
from pathlib import Path
import hashlib,json,shutil,plistlib,subprocess,sys,os,importlib.metadata as md,struct
root=Path(__file__).resolve().parents[3];arch=sys.argv[1];target=sys.argv[2];minimum=sys.argv[3]
version=os.environ.get('LABORATOIRE_DISTRIBUTION_VERSION','0.5.2-macos-preview.1')
out=root/'dist/macos'/arch;out.mkdir(parents=True,exist_ok=True)
app=out/'Laboratoire du Photo Club Briançonnais.app'
if app.exists():raise RuntimeError('Bundle exists; use a clean build directory')
native=app/'Contents/MacOS';resources=app/'Contents/Resources';native.mkdir(parents=True);resources.mkdir()
shutil.copy2(root/'target'/target/'release/lightcraft',native/'Laboratoire')
shutil.copy2(root/'target'/target/'release/lightcraft-cli',native/'laboratoire-cli')
shutil.copytree(root/'ai/dist/PhotoLabAI',resources/'ai',symlinks=True)
shutil.copytree(root/'dist/models',resources/'models')
for item in json.loads((root/'packaging/club/models-manifest.json').read_text()):
 file=resources/'models'/item['file'];assert hashlib.file_digest(file.open('rb'),'sha256').hexdigest()==item['sha256']
shutil.copy2(root/'assets/club/club.icns',resources/'club.icns')
(native/'ai-runtime.json').write_text(json.dumps({'worker':'../Resources/ai/PhotoLabAI','models':'../Resources/models','results':'resultats-ia','provider':'CPUExecutionProvider'},indent=2)+'\n')
info={'CFBundleName':'Laboratoire du Photo Club Briançonnais','CFBundleDisplayName':'Laboratoire du Photo Club Briançonnais','CFBundleExecutable':'Laboratoire','CFBundleIdentifier':'fr.photoclub.brianconnais.laboratoire','CFBundleIconFile':'club.icns','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.5.2','CFBundleVersion':'0.5.2','LSMinimumSystemVersion':minimum,'NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','NSHumanReadableCopyright':'Based on LightCraft. MIT OR Apache-2.0; segment Apache-2.0. See bundled NOTICE and licenses.'}
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
lic=resources/'licences';lic.mkdir()
for name in ['licences-dependances','licences-polices']:
 shutil.copytree(root/'packaging/club/licences'/name,lic/name)
for file in (root/'packaging/club/licences').iterdir():
 if file.is_file() and not file.name.startswith(('Microsoft-','Inno-')):shutil.copy2(file,lic/file.name)
inventory=[]
for name in ['numpy','opencv-python-headless','onnxruntime','tifffile','psutil','pyinstaller','pyinstaller-hooks-contrib']:
 dist=md.distribution(name);folder=lic/'python-macos'/name;folder.mkdir(parents=True)
 for file in dist.files or []:
  src=Path(dist.locate_file(file));base=src.name.lower()
  if src.is_file() and any(s in base for s in ['license','licence','notice','copying']) and src.suffix not in ['.py','.pyc']:
   shutil.copy2(src,folder/str(file).replace('/','_'))
 inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License')})
(lic/'python-macos/INVENTAIRE.json').write_text(json.dumps(inventory,indent=2))
for name in ['LICENSE-MIT','LICENSE-APACHE','NOTICE']:shutil.copy2(root/name,resources/name)
shutil.copy2(root/'docs/MACOS-CLUB.md',out/'INSTALLATION-MAC.md')
shutil.copy2(root/'docs/MACOS-CLUB.md',resources/'INSTALLATION-MAC.md')
# Sign Mach-O files inside-out. These ad-hoc signatures validate binary integrity,
# but are not Developer ID signatures and do not provide Apple notarization.
magics={b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf'}
for file in sorted(app.rglob('*'),key=lambda p:len(p.parts),reverse=True):
 if not file.is_file() or file.is_symlink():continue
 with file.open('rb') as stream:magic=stream.read(4)
 if magic in magics:subprocess.run(['codesign','--force','--sign','-',str(file)],check=True)
for framework in sorted(app.rglob('*.framework'),key=lambda p:len(p.parts),reverse=True):
 subprocess.run(['codesign','--force','--sign','-',str(framework)],check=True)
subprocess.run(['codesign','--force','--sign','-',str(app)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
for file in app.rglob('*'):
 if file.is_file() and any(bad in file.name.lower() for bad in ['avcodec','avformat','x264','gnutls','libintl','libnettle']):
  raise RuntimeError('Unwanted third-party multimedia dependency: '+file.name)
print(app)
