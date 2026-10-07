from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from clinic.models import Enrollment
from clinic.services import queue_email
class Command(BaseCommand):
    help='Encola alertas Canitas desde 15 días antes del fin; recupera días omitidos.'
    def handle(self,*args,**kwargs):
        today=timezone.localdate(); count=0
        ids=Enrollment.objects.filter(invoice__status='PAID',ends__gt=today,ends__lte=today+timedelta(days=15),alert_sent_at__isnull=True).values_list('pk',flat=True)
        for pk in ids:
            with transaction.atomic():
                e=Enrollment.objects.select_for_update().get(pk=pk)
                if e.alert_sent_at: continue
                queue_email(e.owner.email,'Renovación Plan Canitas',f'Tu Plan Canitas vence el {e.ends}. Contacta recepción para renovar.')
                e.alert_sent_at=timezone.now(); e.save(); count+=1
        self.stdout.write(f'{count} alertas encoladas. Ejecuta send_notifications para enviarlas.')
