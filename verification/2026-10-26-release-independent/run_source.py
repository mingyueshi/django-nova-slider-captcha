from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path.cwd();out=Path('/tmp/nova-slider-release-review-20261026')
label=sys.argv[1]
files=[p for p in (root/'src/nova_slider_captcha').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
identity={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/(label+'-runtime.json')).write_text(json.dumps(identity,indent=2)+'\n')
env={**os.environ,'PYTHONPATH':'src:.','DJANGO_SETTINGS_MODULE':'tests.settings','NOVA_TEST_DB':str(out/(label+'.sqlite3'))}
commands=[[sys.executable,'-c','import sys,django,PIL; print(sys.version); print("Django",django.get_version(),"Pillow",PIL.__version__)'],[sys.executable,'-m','django','check'],[sys.executable,'-m','django','makemigrations','nova_slider_captcha','--check','--dry-run'],[sys.executable,'-m','django','test','tests','--noinput','-v','1'],['uv','pip','check','--python',sys.executable]]
with (out/(label+'.log')).open('w') as log:
    for command in commands:
        log.write('COMMAND '+ ' '.join(command)+'\n');log.flush()
        result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise SystemExit(result.returncode)
assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in identity.items()),'Runtime changed during check'
print(label+' passed; runtime stable during checks')
