"""Operaciones transaccionales. Las vistas nunca modifican el dinero directamente."""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from .models import *

def audit(actor, action, obj):
    Audit.objects.create(actor=actor,action=action,target=f'{type(obj).__name__}:{obj.pk}')

def allow(actor, *roles):
    if not actor.is_active or (not actor.is_superuser and actor.role not in roles): raise PermissionDenied

def clinical(actor, consultation):
    allow(actor,'ADMIN','VET')
    if actor.role == 'VET' and consultation.appointment.vet_id != actor.pk: raise PermissionDenied

def queue_email(recipient, subject, body):
    Notification.objects.create(recipient=recipient,subject=subject,body=body)

@transaction.atomic
def save_shift(actor, obj):
    allow(actor,'ADMIN')
    # Un candado global de agenda serializa citas/turnos y cambios de cobertura.
    list(User.objects.select_for_update().filter(role='VET').order_by('pk'))
    obj.full_clean(); obj.save(); audit(actor,'guardar turno',obj)
    return obj

@transaction.atomic
def save_appointment(actor, obj):
    allow(actor,'ADMIN','RECEPTION')
    list(User.objects.select_for_update().filter(role='VET').order_by('pk'))
    if obj.pk:
        old = Appointment.objects.select_for_update().get(pk=obj.pk)
        if old.status != 'SCHEDULED': raise ValidationError('Sólo se reprograman citas programadas.')
    if obj.starts <= timezone.now(): raise ValidationError('La cita debe ser futura.')
    obj.status = 'SCHEDULED'
    obj.full_clean(); obj.save(); audit(actor,'agendar o reprogramar cita',obj)
    queue_email(obj.pet.owner.email,'Cita SweetPets',f'{obj.pet.name}: {timezone.localtime(obj.starts):%d/%m/%Y %H:%M}. Veterinario: {obj.vet}.')
    queue_email(obj.vet.email,'Agenda SweetPets',str(obj))
    return obj

@transaction.atomic
def cancel_appointment(actor, pk, reason=''):
    allow(actor,'ADMIN','RECEPTION')
    list(User.objects.select_for_update().filter(role='VET').order_by('pk'))
    a = Appointment.objects.select_for_update().get(pk=pk)
    if a.status != 'SCHEDULED': raise ValidationError('Sólo se cancelan citas programadas.')
    a.status = 'CANCELLED'; a.reason = reason or a.reason; a.save()
    audit(actor,'cancelar cita',a)
    queue_email(a.pet.owner.email,'Cita cancelada',str(a))
    return a

def active_plan(pet, date=None):
    date = date or timezone.localdate()
    # Plan comprado: los beneficios comienzan al completar el pago.
    return Enrollment.objects.filter(pets=pet,starts__lte=date,ends__gt=date,invoice__status='PAID').first()

@transaction.atomic
def add_item(invoice, service, quantity=1, price=None, exam_kind='', apply_plan=True):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != 'PENDING' or invoice.payments.exists():
        raise ValidationError('No se modifica una factura con pagos. Genera otra factura por el servicio adicional.')
    plan = active_plan(invoice.pet) if invoice.pet_id and apply_plan else None
    discount, included = Decimal('0'),False
    if plan:
        plan = Enrollment.objects.select_for_update().get(pk=plan.pk)
        if exam_kind:
            used = InvoiceItem.objects.filter(benefit_plan=plan,exam_kind=exam_kind,included=True).aggregate(n=models.Sum('quantity'))['n'] or 0
            if used + quantity <= plan.included_exams.get(exam_kind,0):
                discount,included = Decimal('100'),True
        if not included and service.kind in ['CONSULT','EXAM','HOSPITAL','SPA']:
            discount = plan.discount_percent
    item = InvoiceItem(invoice=invoice,service=service,description=service.name,quantity=quantity,unit_price=service.price if price is None else price,unit_cost=service.cost,tax_percent=service.tax_percent,discount_percent=discount,benefit_plan=plan,exam_kind=exam_kind,included=included)
    item.full_clean(); item.save()
    if invoice.total == 0:
        invoice.status="PAID"; invoice.save()
    return item

def pending_invoice(consultation):
    invoice = Invoice.objects.filter(consultation=consultation,status='PENDING',payments__isnull=True).order_by('-pk').first()
    if invoice is None:
        pet = consultation.appointment.pet
        invoice = Invoice.objects.create(consultation=consultation,owner=pet.owner,pet=pet)
    return invoice

@transaction.atomic
def finish_consultation(actor, obj, medications):
    a = Appointment.objects.select_for_update().get(pk=obj.appointment_id)
    allow(actor,'ADMIN','VET')
    if actor.role == 'VET' and a.vet_id != actor.pk: raise PermissionDenied
    if a.status not in ['SCHEDULED','IN_PROGRESS']: raise ValidationError('La cita no está pendiente.')
    if a.starts > timezone.now(): raise ValidationError('La cita todavía no comienza.')
    obj.full_clean(); obj.save()
    for data in medications:
        m = Medication(consultation=obj,**data); m.full_clean(); m.save()
    a.status = 'ATTENDED'; a.save()
    inv = pending_invoice(obj)
    add_item(inv,a.service)
    audit(actor,'registrar consulta y factura',obj)
    return obj

@transaction.atomic
def finish_spa(actor, pk):
    allow(actor,'ADMIN','RECEPTION')
    a = Appointment.objects.select_for_update().get(pk=pk)
    if a.service.kind != 'SPA' or a.status != 'SCHEDULED' or a.starts > timezone.now(): raise ValidationError('El spa debe haber comenzado y estar programado.')
    inv = Invoice.objects.create(owner=a.pet.owner,pet=a.pet)
    add_item(inv,a.service)
    a.status='ATTENDED'; a.save(); audit(actor,'cerrar spa',a)
    return inv

@transaction.atomic
def save_exam(actor, obj):
    clinical(actor,obj.consultation)
    if obj.pk:
        old = Exam.objects.select_for_update().get(pk=obj.pk)
        if old.consultation_id != obj.consultation_id or old.service_id != obj.service_id or old.kind != obj.kind:
            raise ValidationError('No cambies la consulta, el tipo o la tarifa de un examen existente.')
    obj.full_clean()
    new = obj.pk is None
    if new:
        inv = pending_invoice(obj.consultation)
        add_item(inv,obj.service,exam_kind=obj.kind)
    obj.save(); audit(actor,'guardar examen',obj)
    return obj

@transaction.atomic
def admit(actor, obj):
    clinical(actor,obj.consultation)
    pet = Pet.objects.select_for_update().get(pk=obj.consultation.appointment.pet_id)
    if Hospitalization.objects.filter(consultation__appointment__pet=pet,discharged_at__isnull=True).exists():
        raise ValidationError('La mascota ya está hospitalizada.')
    obj.full_clean(); obj.save(); audit(actor,'hospitalizar',obj)
    return obj

def billed_days(start,end):
    if end <= start: raise ValidationError('El alta debe ser posterior al ingreso.')
    return max(1,int((Decimal(str((end-start).total_seconds()))/Decimal('86400')).to_integral_value(rounding=ROUND_CEILING)))

@transaction.atomic
def discharge(actor, pk, end, summary):
    h = Hospitalization.objects.select_for_update().get(pk=pk)
    clinical(actor,h.consultation)
    if h.discharged_at: raise ValidationError('Esta hospitalización ya tiene alta.')
    if end > timezone.now(): raise ValidationError('El alta no puede ser futura.')
    if not summary.strip(): raise ValidationError('El resumen de alta es obligatorio.')
    days = billed_days(h.admitted_at,end)
    h.discharged_at=end; h.summary=summary; h.full_clean()
    inv=pending_invoice(h.consultation)
    add_item(inv,h.service,quantity=days,price=h.daily_rate)
    h.save(); audit(actor,'alta hospitalaria',h)
    return h

@transaction.atomic
def add_hospital_note(actor, h, text):
    h=Hospitalization.objects.select_for_update().get(pk=h.pk)
    clinical(actor,h.consultation)
    if h.discharged_at: raise ValidationError('La hospitalización ya está cerrada.')
    n=HospitalNote(hospitalization=h,author=actor,text=text); n.full_clean(); n.save()
    audit(actor,'bitácora hospitalaria',n)
    return n

@transaction.atomic
def enroll(actor, owner, pets, config, starts=None):
    allow(actor,'ADMIN','RECEPTION')
    owner = Customer.objects.select_for_update().get(pk=owner.pk)
    pets=list(pets); starts=starts or timezone.localdate()
    if starts != timezone.localdate(): raise ValidationError('Las nuevas inscripciones comienzan hoy.')
    if not owner.active or not config.active: raise ValidationError('Propietario o configuración inactivos.')
    if not 1 <= len(pets) <= 2 or len({p.pk for p in pets}) != len(pets): raise ValidationError('Selecciona una o dos mascotas distintas.')
    ends=starts+relativedelta(months=config.months)
    validate_plan_pets(owner,pets,starts,ends)
    config.full_clean()
    e=Enrollment.objects.create(owner=owner,config=config,starts=starts,ends=ends,price=config.price,discount_percent=config.discount_percent,included_exams=config.included_exams)
    e.pets.set(pets)
    inv=Invoice.objects.create(owner=owner,enrollment=e)
    service,_=Service.objects.get_or_create(name='Inscripción Plan Canitas',kind='PLAN',defaults={'price':config.price,'cost':0,'tax_percent':0})
    add_item(inv,service,price=e.price,apply_plan=False)
    audit(actor,'inscripción Canitas',e)
    return e

def validate_plan_pets(owner,pets,starts,ends,exclude=None):
    for p in pets:
        if p.owner_id != owner.pk or not p.active or not p.eligible(starts):
            raise ValidationError('Cada mascota debe tener al menos 8 años, estar activa y pertenecer al mismo dueño.')
        if Enrollment.objects.filter(pets=p,starts__lt=ends,ends__gt=starts).exclude(pk=exclude).exists():
            raise ValidationError('La mascota tiene otra inscripción que se solapa, incluso si está pendiente de pago.')

@transaction.atomic
def add_plan_pet(actor, pk, pet):
    allow(actor,'ADMIN','RECEPTION')
    e=Enrollment.objects.select_for_update().get(pk=pk)
    Customer.objects.select_for_update().get(pk=e.owner_id)
    if not (e.starts <= timezone.localdate() < e.ends) or e.pets.count() >= 2: raise ValidationError('Plan vencido o ya cubre dos mascotas.')
    validate_plan_pets(e.owner,[pet],e.starts,e.ends,exclude=e.pk)
    if e.pets.filter(pk=pet.pk).exists(): raise ValidationError('La mascota ya pertenece al plan.')
    e.pets.add(pet); audit(actor,'agregar segunda mascota Canitas',e)
    return e

@transaction.atomic
def pay(actor, pk, amount, tendered, method, reference='', key=None):
    allow(actor,'ADMIN','RECEPTION')
    inv=Invoice.objects.select_for_update().get(pk=pk)
    key=key or uuid4()
    previous=Payment.objects.filter(key=key).first()
    if previous:
        if previous.invoice_id != inv.pk: raise ValidationError('Identificador de pago inválido.')
        return previous
    amount,tendered=Decimal(str(amount)),Decimal(str(tendered))
    if method not in dict(Payment._meta.get_field('method').choices): raise ValidationError('Método inválido.')
    if amount <= 0 or amount > inv.balance or tendered < amount: raise ValidationError('Abono mayor a cero, menor o igual al saldo, y recibido suficiente.')
    if method != 'CASH' and tendered != amount: raise ValidationError('Sólo el efectivo admite cambio.')
    p=Payment(invoice=inv,amount=amount,tendered=tendered,change=tendered-amount,method=method,reference=reference,key=key)
    p.full_clean(); p.save()
    inv.status='PAID' if inv.balance == 0 else 'PARTIAL'; inv.save()
    audit(actor,'registrar pago',p)
    queue_email(inv.owner.email,f'Comprobante SweetPets #{inv.pk}',f'Abono: ${amount}. Cambio: ${p.change}. Saldo: ${inv.balance}. Puedes solicitar el PDF en recepción.')
    return p
