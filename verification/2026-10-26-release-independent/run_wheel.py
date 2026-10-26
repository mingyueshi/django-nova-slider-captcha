from pathlib import Path
import os,subprocess,sys
root=Path.cwd();out=Path('/tmp/nova-slider-release-review-20261026');label=sys.argv[1]
env={**os.environ,'PYTHONPATH':'.','DJANGO_SETTINGS_MODULE':'tests.settings','NOVA_TEST_DB':str(out/(label+'.sqlite3'))}
commands=[[sys.executable,'-c','import pathlib,nova_slider_captcha,django; p=pathlib.Path(nova_slider_captcha.__file__).resolve(); print(p); print(nova_slider_captcha.__version__,django.get_version()); assert "site-packages" in p.parts'],[sys.executable,'-m','django','check'],[sys.executable,'-m','django','makemigrations','nova_slider_captcha','--check','--dry-run'],[sys.executable,'-m','django','test','tests','--noinput','-v','1'],['uv','pip','check','--python',sys.executable]]
with (out/(label+'.log')).open('w') as log:
    for command in commands:
        log.write('COMMAND '+' '.join(command)+'\n');log.flush();result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise SystemExit(result.returncode)
print(label+' passed using installed wheel')
