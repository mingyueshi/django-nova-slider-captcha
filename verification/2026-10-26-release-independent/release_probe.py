"""Independent negative release-gate checks; modifies temporary copies only."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile,zipfile
import yaml
root=Path.cwd();out=Path('/tmp/nova-slider-release-review-20261026')
checker=root/'scripts/check_release.py'
results=[]
for tag in ['v0.3.1','v0.3.0rc1','0.3.0']:
    result=subprocess.run([sys.executable,str(checker),'--tag',tag],capture_output=True,text=True)
    assert result.returncode!=0,(tag,result.stdout)
    results.append('reject mismatched tag '+tag)
with tempfile.TemporaryDirectory(prefix='nova-release-negative-') as folder:
    target=Path(folder);wheel=out/'dist/nova_slider_captcha-0.3.0-py3-none-any.whl'
    shutil.copy2(out/'dist/nova_slider_captcha-0.3.0.tar.gz',target)
    with zipfile.ZipFile(wheel) as original,zipfile.ZipFile(target/wheel.name,'w') as broken:
        for info in original.infolist():
            if not info.filename.endswith('migrations/0003_challenge_policy.py'):
                broken.writestr(info,original.read(info.filename))
    result=subprocess.run([sys.executable,str(checker),'--dist',str(target)],capture_output=True,text=True)
    assert result.returncode!=0 and '0003_challenge_policy' in result.stderr
    results.append('reject wheel missing policy migration')
workflows={p.name:yaml.load(p.read_text(),Loader=yaml.BaseLoader) for p in (root/'.github/workflows').glob('*.yml')}
tests,publish=workflows['tests.yml'],workflows['publish.yml']
assert {(row['python'],row['django']) for row in tests['jobs']['django']['strategy']['matrix']['include']}=={('3.10','5.2.17'),('3.12','5.2.17'),('3.12','6.1.2'),('3.13','6.1.2')}
assert set(publish['on'])=={'release'} and publish['on']['release']['types']==['published']
assert publish['jobs']['verify']['uses']=='./.github/workflows/tests.yml'
assert set(publish['jobs']['publish']['needs'])=={'verify','version'}
assert publish['jobs']['publish']['environment']['name']=='pypi'
assert publish['jobs']['publish']['permissions']=={'id-token':'write'}
for workflow in (tests,publish):
    for name,job in workflow['jobs'].items():
        assert 'runner.' not in json.dumps(job.get('env',{}))
        if name!='publish':assert job.get('permissions',{}).get('id-token')!='write'
psteps=publish['jobs']['publish']['steps'];assert len(psteps)==2
assert psteps[0]['uses'].startswith('actions/download-artifact@') and psteps[1]['uses'].startswith('pypa/gh-action-pypi-publish@')
upload=next(s for s in tests['jobs']['build']['steps'] if s.get('uses','').startswith('actions/upload-artifact@'))
download=next(s for s in tests['jobs']['django']['steps'] if s.get('uses','').startswith('actions/download-artifact@'))
assert upload['with']['name']==download['with']['name']==psteps[0]['with']['name']=='python-distributions'
results.append('release-only gate, four version pairs, least-privilege upload and same artifact across tests/publication')
identity={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((root/'.github/workflows').glob('*.yml'))+[checker]}
print(json.dumps({'status':'passed','checks':results,'workflow_sha256':identity,'limitations':['Static and local checks only; no GitHub runner or PyPI OIDC exchange was invoked.']},indent=2))
