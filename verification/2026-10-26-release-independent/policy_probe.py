"""Independent policy and migration acceptance; uses only in-memory SQLite."""
import io,json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import django
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:'
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.utils import timezone
from nova_slider_captcha import services
from nova_slider_captcha.conf import challenge_policy
from nova_slider_captcha.checks import captcha_settings_check

old_target=[('nova_slider_captcha','0002_ratelimitstate')]
executor=MigrationExecutor(connection);executor.migrate(old_target)
Old=executor.loader.project_state(old_target).apps.get_model('nova_slider_captcha','Challenge')
now=timezone.now(); request=SimpleNamespace(session={'_nova_slider_binding':'review-only-session'})
old=Old.objects.create(session_hash=services.session_binding(request),purpose='demo',target_x=100,expires_at=now+timedelta(seconds=120),attempts=4)
old_values={key:getattr(old,key) for key in ('id','expires_at','attempts','session_hash','target_x')}
with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=20,NOVA_SLIDER_TOLERANCE=10):
    executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
from nova_slider_captcha.models import Challenge
old=Challenge.objects.get(pk=old.pk)
assert (old.max_attempts,old.tolerance)==(5,4)
assert all(getattr(old,key)==value for key,value in old_values.items())
checks=['0002 to current migration preserves old data and literal 5/4 policy despite new 20/10 settings']
with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=20,NOVA_SLIDER_TOLERANCE=10):
    rejected=services.verify(request,old.pk,105)
    assert rejected=={'ok':False,'code':'incorrect','attemptsRemaining':0},rejected
    assert services.verify(request,old.pk,100)['code']=='attempts_exhausted'
checks.append('old tolerance stays 4 and old fifth attempt exhausts despite relaxed current policy')
with override_settings(NOVA_SLIDER_CHALLENGE_TTL=600,NOVA_SLIDER_MAX_ATTEMPTS=2,NOVA_SLIDER_TOLERANCE=0):
    with patch.object(services.timezone,'now',return_value=now): issued=services.issue(request,'demo')
row=Challenge.objects.get(pk=issued['challengeId'])
assert (row.max_attempts,row.tolerance,issued['expiresIn'],issued['maxAttempts'])==(2,0,600,2)
assert row.expires_at==now+timedelta(seconds=600)
with override_settings(NOVA_SLIDER_CHALLENGE_TTL=30,NOVA_SLIDER_MAX_ATTEMPTS=20,NOVA_SLIDER_TOLERANCE=10):
    assert services.verify(request,row.pk,row.target_x+1)['attemptsRemaining']==1
    result=services.verify(request,row.pk,row.target_x)
    assert result['ok'] and result['expiresIn']==60
    assert services.consume(result['token'],request,'demo')
    assert not services.consume(result['token'],request,'demo')
checks.append('new strict policy and 600-second lifetime survive later settings changes; token remains 60-second and one-use')
for setting,minimum,maximum in [('NOVA_SLIDER_CHALLENGE_TTL',30,600),('NOVA_SLIDER_MAX_ATTEMPTS',1,20),('NOVA_SLIDER_TOLERANCE',0,10)]:
    for value in [True,False,None,str(minimum),minimum-1,maximum+1,1.5,[],{}]:
        with override_settings(**{setting:value}):
            assert any(e.id=='nova_slider_captcha.E006' for e in captcha_settings_check(None)),(setting,value)
            try:challenge_policy()
            except ValueError:pass
            else:raise AssertionError((setting,value))
    for value in (minimum,maximum):
        with override_settings(**{setting:value}):challenge_policy()
checks.append('all three settings reject bool/string/non-integer/out-of-range and accept both boundaries')
with override_settings(NOVA_SLIDER_CHALLENGE_TTL=30):
    with patch.object(services.timezone,'now',return_value=now): packet=services.issue(request,'demo')
row=Challenge.objects.get(pk=packet['challengeId'])
with patch.object(services.timezone,'now',return_value=now+timedelta(seconds=30)):
    assert services.verify(request,row.pk,row.target_x)['code']=='expired'
checks.append('challenge expires at exact configured timestamp')
print(json.dumps({'status':'passed','checks':checks},indent=2))
