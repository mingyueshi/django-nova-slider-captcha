import re
import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from demo.models import ProfileApproval
from demo.profile import APPROVAL_SECONDS, approval_hash, eligible_accounts


class Command(BaseCommand):
    help = "本地演示。仅在通过预先核实的渠道确认登记用户身份后，批准一次显示名称更改。"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("reference", help="用户从当前已登录的非视觉页面读取的核验编号")

    def handle(self, *, username, reference, **options):
        if not re.fullmatch(r"[0-9a-f]{64}", reference):
            raise CommandError("请提供非视觉页面显示的完整核验编号。")
        user = eligible_accounts().filter(username=username).first()
        if user is None:
            raise CommandError("只能批准已预登记且启用的演示账号。")
        code = secrets.token_urlsafe(32)
        ProfileApproval.objects.update_or_create(user=user, defaults={
            "session_reference": reference, "code_hash": approval_hash(code),
            "expires_at": timezone.now() + timedelta(seconds=APPROVAL_SECONDS),
            "attempts": 0, "consumed": False,
        })
        self.stdout.write(code)
