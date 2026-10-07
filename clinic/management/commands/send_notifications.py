from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from clinic.models import Notification
class Command(BaseCommand):
    help='Envía la cola de notificaciones pendiente y conserva errores para reintentar.'
    def handle(self,*args,**kwargs):
        sent=0
        for pk in Notification.objects.filter(sent_at__isnull=True).values_list('pk',flat=True):
            with transaction.atomic():
                n=Notification.objects.select_for_update().get(pk=pk)
                if n.sent_at: continue
                try:
                    send_mail(n.subject,n.body,settings.DEFAULT_FROM_EMAIL,[n.recipient],fail_silently=False)
                    n.sent_at=timezone.now(); n.error=''; sent+=1
                except Exception as e: n.error=str(e)[:1000]
                n.save()
        self.stdout.write(f'{sent} notificaciones enviadas. SMTP ofrece entrega al menos una vez; verifica errores en admin.')
