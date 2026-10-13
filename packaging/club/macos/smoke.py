"""Native CPU inference, library persistence and GUI checks against the actual bundle."""
from pathlib import Path
import json,subprocess,hashlib,time,os,socket,sys
import numpy as np,tifffile
root=Path(__file__).resolve().parents[3];arch=sys.argv[1];out=root/'dist/macos'/arch
app=out/'Laboratoire du Photo Club Briançonnais.app';native=app/'Contents/MacOS';res=app/'Contents/Resources'
test=root/'dist/macos-tests'/arch;test.mkdir(parents=True,exist_ok=True)
report={'arch':arch,'os':os.uname().release,'pythonRequiredForUser':False,'signing':'ad-hoc; not notarized','aiProvider':'CPUExecutionProvider','tests':{}}
y,x=np.mgrid[:256,:320];clean=np.stack([.18+.35*x/320,.2+.25*y/256,.3+.12*x/320],axis=-1).astype(np.float32)
image=np.clip(clean+np.random.default_rng(41).normal(0,.035,clean.shape),0,1).astype(np.float32)
for op in ['denoise','inpaint']:
 d=test/op;d.mkdir(exist_ok=True);source=d/'input.tif';output=d/'output.tif'
 img=image.copy()
 if op=='inpaint':img[105:150,130:170]=[.8,.02,.03]
 tifffile.imwrite(source,img,photometric='rgb',metadata=None);before=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
 job={'operation':op,'input':str(source),'output':str(output),'models':str(res/'models'),'strength':.9,'mode':'comfort','provider':'CPUExecutionProvider','data_dir':str(d/'runtime'),'progress':str(d/'progress.json'),'result':str(d/'result.json'),'strokes':[{'points':[[.47,.42],[.47,.58]],'radius':.08}] if op=='inpaint' else []}
 j=d/'job.json';j.write_text(json.dumps(job));env=os.environ.copy();env['PATH']='/usr/bin:/bin';env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
 started=time.monotonic()
 with (d/'stderr.log').open('w') as log:p=subprocess.run([str(res/'ai/PhotoLabAI'),str(j)],env=env,cwd=str(d),stdout=log,stderr=log,timeout=600)
 if p.returncode:raise RuntimeError((d/'stderr.log').read_text())
 result=tifffile.imread(output);assert result.shape==img.shape and result.dtype==np.float32 and np.isfinite(result).all()
 assert hashlib.file_digest(source.open('rb'),'sha256').hexdigest()==before
 if op=='denoise':
  noisy=float(np.mean((img-clean)**2));denoised=float(np.mean((result-clean)**2));assert denoised<noisy
  report['tests'][op]={'seconds':round(time.monotonic()-started,2),'noisyMSE':noisy,'denoisedMSE':denoised,'sourceUnchanged':True}
 else:
  center=result[110:140,138:160].mean((0,1));assert center[0]-center[1]<.18 and np.array_equal(result[:40],img[:40])
  report['tests'][op]={'seconds':round(time.monotonic()-started,2),'centerRGB':center.tolist(),'unmaskedUnchanged':True,'sourceUnchanged':True}
# CLI uses exactly the Rust executable shipped inside the app; reopen the same library.
library=test/'bibliothèque';script=test/'catalog.jsonl'
script.write_text('\n'.join(json.dumps(v) for v in [
 {'command':'photo.rate','params':{'rating':4}},
 {'command':'develop.set','params':{'control':'light.exposure','value':.5}},
 {'command':'album.create','params':{'name':'Essai Mac','addSelected':True}},
 {'command':'library.info','params':{}}])+'\n')
cmd=[str(native/'laboratoire-cli'),'run','--library',str(library),'--import',str(test/'denoise/input.tif'),'--script',str(script)]
p=subprocess.run(cmd,capture_output=True,text=True,timeout=180);assert p.returncode==0,p.stdout+p.stderr
(test/'cli-first.log').write_text(p.stdout+p.stderr)
query=test/'query.jsonl';query.write_text('\n'.join(json.dumps(v) for v in [{'command':'catalog.query','params':{'filter':{}}},{'command':'library.info','params':{}},{'command':'develop.get','params':{'id':1}}])+'\n')
p=subprocess.run([str(native/'laboratoire-cli'),'run','--library',str(library),'--script',str(query)],capture_output=True,text=True,timeout=180)
assert p.returncode==0,p.stdout+p.stderr
lines=[json.loads(line) for line in p.stdout.splitlines() if line.startswith('{')]
by_command={line['command']:line['result'] for line in lines if line['ok']}
assert len(by_command['catalog.query']['photos'])==1 and by_command['catalog.query']['photos'][0]['rating']==4,p.stdout
assert by_command['library.info']['persistent'] and by_command['library.info']['albums']==1,p.stdout
assert by_command['develop.get']['light']['exposure']==.5,p.stdout
report['tests']['cliLibrary']={'persistent':True,'ratingPreserved':True,'albumAndDevelopPreserved':True}
# Start the native .app executable in an isolated profile and ask its own control server for a snapshot.
env=os.environ.copy();env.update(PHOTOLAB_CLUB_DATA=str(test/'profil'),LIGHTCRAFT_LIBRARY=str(library),LIGHTCRAFT_GPU_BACKEND='off')
log=(test/'gui.log').open('w');proc=subprocess.Popen([str(native/'Laboratoire'),'--control','19115'],env=env,stdout=log,stderr=log)
try:
 for attempt in range(120):
  try:s=socket.create_connection(('127.0.0.1',19115),timeout=2);break
  except OSError:
   if proc.poll() is not None:raise RuntimeError((test/'gui.log').read_text())
   time.sleep(.5)
 else:raise RuntimeError('Native GUI control did not start')
 s.settimeout(60);stream=s.makefile('rwb');idx=0
 def call(method,params={}):
  global idx
  idx+=1;stream.write((json.dumps({'id':idx,'method':method,'params':params})+'\n').encode());stream.flush();v=json.loads(stream.readline());assert v['ok'],v;return v['result']
 state=call('ui.inspect');assert state['ui']['language']=='fr' and not state['libraryProblem'],state
 call('engine.execute',{'command':'library.select','params':{'ids':[1],'active':1}})
 call('engine.execute',{'command':'ai.denoise','params':{'strength':.75,'mode':'comfort','preview':True}})
 for i in range(600):
  ai=call('ui.inspect')['ai']
  if not ai['running']:break
  time.sleep(.5)
 assert ai['lastResult'] and Path(ai['lastResult']).is_file(),ai
 call('engine.execute',{'command':'ai.result','params':{}})
 for i in range(100):
  info=call('engine.execute',{'command':'library.info','params':{}})
  if info['photos']==2:break
  time.sleep(.2)
 assert info['photos']==2,info
 report['tests']['guiInference']={'resultCreated':True,'relativeBundlePathsWork':True,'resultImported':True}
 call('engine.execute',{'command':'app.about','params':{}})
 call('ui.screenshot',{'path':str(out/'APERCU-MAC.png'),'headless':True})
 call('app.quit');proc.wait(timeout=45);assert proc.returncode==0
 report['tests']['gui']={'started':True,'french':True,'libraryOpened':True,'headlessScreenshot':True}
finally:
 if proc.poll() is None:proc.terminate();proc.wait(timeout=30)
 log.close()
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
report['tests']['bundleSignatureIntegrity']=True
(out/'VALIDATION-MAC.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,indent=2))
