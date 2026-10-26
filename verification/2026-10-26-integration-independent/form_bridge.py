import io,json,sys
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:'
settings.NOVA_SLIDER_PURPOSES=['demo','login','signup']
import django
django.setup()
from django import forms
from django.core.management import call_command
from django.test import Client,RequestFactory
from nova_slider_captcha.forms import SliderCaptchaField,SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge
call_command('migrate',verbosity=0,stdout=io.StringIO())
class Register(SliderCaptchaFormMixin,forms.Form):
    email=forms.EmailField()
    safety=SliderCaptchaField(purpose='signup')
client=Client(enforce_csrf_checks=True)
def request():
    req=RequestFactory().post('/')
    req.session=client.session
    return req
for line in sys.stdin:
    data=json.loads(line)
    try:
        if data.get('op')=='form':
            result={'html':'<form>'+Register(prefix='registration',request=request()).as_p()+'</form>'}
        elif data.get('op')=='answer':
            row=Challenge.objects.get(pk=data['challengeId']); result={'x':row.target_x}
        elif data.get('op')=='submit':
            form=Register(data=data['data'],prefix='registration',request=request())
            result={'valid':form.is_valid(),'errors':form.errors.get_json_data()}
        else:
            method=data.get('method','GET')
            headers={'HTTP_'+k.upper().replace('-','_'):v for k,v in data.get('headers',{}).items() if k.lower()!='content-type'}
            r=client.get(data['path'],**headers) if method=='GET' else client.post(data['path'],data.get('body',''),content_type='application/json',**headers)
            result={'status':r.status_code,'text':r.content.decode()}
        print(json.dumps({'id':data['id'],'result':result}),flush=True)
    except Exception as error:
        print(json.dumps({'id':data['id'],'error':repr(error)}),flush=True)
