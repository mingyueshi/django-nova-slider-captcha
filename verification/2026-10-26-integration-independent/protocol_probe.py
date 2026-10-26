"""Independent HTTP/purpose/log regression probe, isolated in-memory SQLite."""
import io,json,logging
from unittest.mock import patch
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:'
import django
django.setup()
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, RequestFactory, override_settings
from nova_slider_captcha import services
from nova_slider_captcha.models import Challenge,RateLimitState
call_command('migrate',verbosity=0)
checks=[]
class Recorder(logging.Handler):
    def __init__(self): super().__init__(); self.records=[]
    def emit(self, record): self.records.append(record)
recorder=Recorder()
logger=logging.getLogger('nova_slider_captcha')
logger.addHandler(recorder)
logger.setLevel(logging.DEBUG)
with override_settings(NOVA_SLIDER_PURPOSES=['demo','login','signup','reset'],NOVA_SLIDER_RATE_LIMITS={'issue_ip':100,'issue_session':100}):
    client=Client(enforce_csrf_checks=True)
    csrf=client.get('/captcha/init').json()['csrfToken']
    def post(action,body):
        return client.post('/captcha/'+action,json.dumps(body),content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
    unknown=post('challenge',{'purpose':'not-registered'})
    assert unknown.status_code==400
    response=post('challenge',{'purpose':'signup'})
    assert response.status_code==200,response.content
    challenge=Challenge.objects.get(pk=response.json()['challengeId'])
    verified=post('verify',{'challengeId':str(challenge.pk),'x':challenge.target_x})
    assert verified.json()['ok']
    token=verified.json()['token']
    request=RequestFactory().post('/')
    request.session=client.session
    assert not services.consume(token,request,'reset')
    assert not post('submit',{'token':token,'purpose':'demo'}).json()['ok']
    assert services.consume(token,request,'signup')
    assert not services.consume(token,request,'signup')
    checks.append('custom purpose, CSRF-backed HTTP, cross-purpose isolation and one-use consumption')
    RateLimitState.objects.all().delete()
    with override_settings(NOVA_SLIDER_RATE_LIMITS={'issue_ip':2,'issue_session':2}):
        assert post('challenge',{'purpose':'signup'}).status_code==200
        assert post('challenge',{'purpose':'reset'}).status_code==200
        assert post('challenge',{'purpose':'demo'}).status_code==429
    checks.append('purposes share existing action/IP/session capacity')
    RateLimitState.objects.all().delete()
    with override_settings(NOVA_SLIDER_PURPOSES=['signup']):
        assert post('challenge',{'purpose':'login'}).status_code==400
    checks.append('configured collection replaces defaults dynamically')
    with override_settings(NOVA_SLIDER_PURPOSES='signup'):
        assert post('challenge',{'purpose':'signup'}).status_code==503
        assert not services.consume('x'*43,request,'signup')
    checks.append('invalid purpose configuration fails closed')
    before=len(recorder.records)
    with patch('django.db.models.query.QuerySet.update',side_effect=DatabaseError('PRIVATE-DB-ERROR')):
        result=post('verify',{'challengeId':str(challenge.pk),'x':challenge.target_x})
        assert result.status_code==503
        assert 'PRIVATE-DB-ERROR' not in result.content.decode()
    assert len(recorder.records)>before
    records=repr([record.__dict__ for record in recorder.records])
    for secret in [token,client.session.get('_nova_slider_binding'),'PRIVATE-DB-ERROR']:
        assert secret not in records
    checks.append('structured fault events omit token, session secret and database error text')
logger.removeHandler(recorder)
print(json.dumps({'status':'passed','checks':checks},indent=2))
