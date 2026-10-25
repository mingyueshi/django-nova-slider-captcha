"""Independent baseline-vs-candidate GCRA trace; never touches project data."""
import importlib.util
import json
import random
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import django
django.setup()
from django.conf import settings
settings.DATABASES['default']['NAME'] = ':memory:'
from django.core.management import call_command
from django.test.utils import override_settings
from nova_slider_captcha import services
from nova_slider_captcha.models import RateLimitState
call_command('migrate', verbosity=0)
source = subprocess.check_output(['git', 'show', '33b92ec:src/nova_slider_captcha/services.py'], text=True)
spec = importlib.util.spec_from_loader('nova_slider_captcha._review_baseline', loader=None)
baseline = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = baseline
exec(compile(source, 'baseline_services.py', 'exec'), baseline.__dict__)
rng = random.Random(20261026)
clock = datetime(2026, 10, 26, tzinfo=timezone.utc)
trace = []
for i in range(500):
    clock += timedelta(microseconds=rng.choice([-1_000_000, -1, 0, 1, 750_000, 1_000_000, 12_000_000, 61_000_000]))
    trace.append((clock, rng.randrange(4), rng.randrange(8), rng.choice(['issue', 'verify']), rng.choice([2, 3, 11, 60_000]), i % 17 == 0, i % 31 == 0))
def run(module):
    RateLimitState.objects.all().delete()
    results=[]
    for now, ip, session, action, capacity, prune, block in trace:
        request=SimpleNamespace(META={'REMOTE_ADDR':f'192.0.2.{ip}'},session={'_nova_slider_binding':f'review-session-{session}'})
        now_us=module.timestamp_us(now)
        if prune:
            RateLimitState.objects.filter(tat_us__lte=now_us, blocked_until_us__lte=now_us).delete()
        if block:
            key=f'{action}:ip:{module._hash(request.META["REMOTE_ADDR"], "ip")}'
            RateLimitState.objects.update_or_create(key=key, defaults={'blocked_until_us':now_us+20_000_000})
        with override_settings(NOVA_SLIDER_RATE_LIMITS={f'{a}_{s}':capacity for a in ['issue','verify'] for s in ['ip','session']}), patch.object(module.timezone, 'now', return_value=now):
            decision=module.allow_request(request,action)
        states=list(RateLimitState.objects.order_by('key').values_list('key','tat_us','blocked_until_us'))
        results.append((decision.allowed, decision.retry_after, states))
    return results
expected=run(baseline)
actual=run(services)
for i, (left, right) in enumerate(zip(expected, actual)):
    assert left == right, (i, trace[i], left, right)
print(json.dumps({'trace_steps':len(trace),'status':'passed','covers':['clock rollback','refill','configuration changes','IP/session/action isolation','prune','upgrade cooldown','retryAfter','all per-step state']}))
