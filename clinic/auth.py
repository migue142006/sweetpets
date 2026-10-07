from datetime import timedelta
from django.contrib.auth.backends import ModelBackend
from django.db import transaction
from django.utils import timezone
from .models import User, Audit

class LockoutBackend(ModelBackend):
    @transaction.atomic
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password: return None
        user=User.objects.select_for_update().filter(username=username).first()
        ip=request.META.get('REMOTE_ADDR') if request else None
        if user is None:
            User().set_password(password) # Trabajo criptográfico también para usuario inexistente.
            Audit.objects.create(action='login fallido',ip=ip)
            return None
        now=timezone.now()
        if user.locked_until and user.locked_until > now:
            Audit.objects.create(actor=user,action='login bloqueado',ip=ip)
            return None
        if user.locked_until:
            user.failed_attempts=0; user.locked_until=None
        if user.check_password(password) and user.is_active:
            user.failed_attempts=0; user.locked_until=None; user.save()
            Audit.objects.create(actor=user,action='login correcto',ip=ip)
            return user
        user.failed_attempts+=1
        if user.failed_attempts >= 3: user.locked_until=now+timedelta(minutes=15)
        user.save()
        Audit.objects.create(actor=user,action='login fallido',ip=ip)
        return None
