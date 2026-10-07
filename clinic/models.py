from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator, FileExtensionValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from dateutil.relativedelta import relativedelta

ZERO = Decimal('0')
MONEY = dict(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])

def positive_interval(start, end):
    if start and end and end <= start:
        raise ValidationError('La fecha final debe ser posterior a la inicial.')

class User(AbstractUser):
    ROLES = [('ADMIN','Administrador'),('VET','Veterinario'),('RECEPTION','Recepcionista')]
    role = models.CharField('rol', max_length=12, choices=ROLES, default='RECEPTION')
    email = models.EmailField('correo', unique=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'),name='user_email_ci')]
    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        if self.is_superuser: self.role = 'ADMIN'
        # Sólo administradores pueden ingresar al admin de Django.
        self.is_staff = self.role == 'ADMIN' or self.is_superuser
        super().save(*args, **kwargs)
    def __str__(self):
        return self.get_full_name() or self.username

class Customer(models.Model):
    name = models.CharField('nombre completo',max_length=150)
    address = models.CharField('dirección',max_length=250)
    phone = models.CharField('teléfono',max_length=15,validators=[RegexValidator(r'^\d{7,15}$','Ingresa entre 7 y 15 dígitos.')])
    email = models.EmailField('correo',unique=True)
    active = models.BooleanField('activo',default=True)
    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(Lower('email'),name='customer_email_ci')]
    def save(self,*args,**kwargs):
        self.email = self.email.lower().strip()
        super().save(*args,**kwargs)
    def __str__(self): return self.name

class Pet(models.Model):
    owner = models.ForeignKey(Customer,on_delete=models.PROTECT,verbose_name='propietario')
    name = models.CharField('nombre',max_length=100)
    species = models.CharField('especie',max_length=4,choices=[('DOG','Perro'),('CAT','Gato')])
    breed = models.CharField('raza',max_length=100)
    birth_date = models.DateField('fecha de nacimiento')
    weight = models.DecimalField('peso en kg',max_digits=6,decimal_places=2,validators=[MinValueValidator(Decimal('0.01'))])
    notes = models.TextField('alergias e historia inicial',blank=True)
    active = models.BooleanField('activo',default=True)
    def clean(self):
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError('La fecha de nacimiento no puede estar en el futuro.')
        if self.owner_id and not self.owner.active: raise ValidationError('Propietario inactivo.')
    def eligible(self, on_date=None):
        return self.birth_date + relativedelta(years=8) <= (on_date or timezone.localdate())
    def __str__(self): return f'{self.name} — {self.owner.name}'

class Service(models.Model):
    KINDS = [('CONSULT','Consulta'),('EXAM','Examen'),('HOSPITAL','Hospitalización'),('SPA','Spa'),('PRODUCT','Producto'),('PLAN','Plan Canitas')]
    name = models.CharField('nombre',max_length=100)
    kind = models.CharField('tipo',max_length=10,choices=KINDS)
    price = models.DecimalField('precio',**MONEY)
    cost = models.DecimalField('costo directo estimado',**MONEY)
    tax_percent = models.DecimalField('impuesto porcentual',max_digits=5,decimal_places=2,default=0,validators=[MinValueValidator(0),MaxValueValidator(100)])
    active = models.BooleanField('activo',default=True)
    def __str__(self): return f'{self.name} (${self.price})'

class Shift(models.Model):
    vet = models.ForeignKey(User,on_delete=models.PROTECT,limit_choices_to={'role':'VET','is_active':True},verbose_name='veterinario')
    starts = models.DateTimeField('inicio')
    ends = models.DateTimeField('fin')
    kind = models.CharField('turno',max_length=5,choices=[('DAY','Día 08 a 20'),('NIGHT','Noche 20 a 08')])
    class Meta:
        ordering = ['starts']
        constraints = [models.CheckConstraint(condition=models.Q(ends__gt=models.F('starts')),name='shift_positive')]
    def clean(self):
        positive_interval(self.starts,self.ends)
        if not self.starts or not self.ends or not self.vet_id: return
        s,e = timezone.localtime(self.starts),timezone.localtime(self.ends)
        hour = 8 if self.kind == 'DAY' else 20
        if s.hour != hour or s.minute or s.second or s.microsecond or e != s + timedelta(hours=12):
            raise ValidationError('Usa 08:00–20:00 o 20:00–08:00 del día siguiente.')
        if self.vet.role != 'VET' or not self.vet.is_active: raise ValidationError('Selecciona un veterinario activo.')
        other = Shift.objects.exclude(pk=self.pk).filter(starts__lt=self.ends,ends__gt=self.starts)
        if other.filter(vet=self.vet).exists(): raise ValidationError('El veterinario ya tiene un turno solapado.')
        if other.filter(kind=self.kind,starts=self.starts).count() >= (2 if self.kind == 'DAY' else 1):
            raise ValidationError('Máximo dos veterinarios de día y uno de noche.')
        if self.pk:
            old = Shift.objects.get(pk=self.pk)
            for a in Appointment.objects.filter(vet=old.vet,status__in=['SCHEDULED','IN_PROGRESS'],starts__gte=old.starts,ends__lte=old.ends):
                if self.vet_id != old.vet_id or not (self.starts <= a.starts and a.ends <= self.ends):
                    raise ValidationError('Reprograma las citas del turno antes de modificarlo.')
    def __str__(self): return f'{self.vet} {self.starts:%Y-%m-%d %H:%M}'

class Appointment(models.Model):
    STATUS = [('SCHEDULED','Programada'),('IN_PROGRESS','En curso'),('ATTENDED','Atendida'),('CANCELLED','Cancelada')]
    pet = models.ForeignKey(Pet,on_delete=models.PROTECT,verbose_name='mascota')
    vet = models.ForeignKey(User,on_delete=models.PROTECT,verbose_name='veterinario',limit_choices_to={'role':'VET','is_active':True})
    service = models.ForeignKey(Service,on_delete=models.PROTECT,verbose_name='servicio')
    starts = models.DateTimeField('inicio')
    ends = models.DateTimeField('fin')
    status = models.CharField('estado',max_length=15,choices=STATUS,default='SCHEDULED')
    reason = models.TextField('motivo o notas',blank=True)
    class Meta:
        ordering = ['-starts']
        constraints = [models.CheckConstraint(condition=models.Q(ends__gt=models.F('starts')),name='appointment_positive')]
    def clean(self):
        positive_interval(self.starts,self.ends)
        if not self.vet_id or not self.pet_id or not self.starts or not self.ends: return
        if self.vet.role != 'VET' or not self.vet.is_active: raise ValidationError('Veterinario inactivo o rol inválido.')
        if not self.pet.active or not self.pet.owner.active: raise ValidationError('Mascota o propietario inactivo.')
        if not self.service.active or self.service.kind not in ['CONSULT','SPA']: raise ValidationError('Agenda una consulta o spa activo.')
        if self.status in ['SCHEDULED','IN_PROGRESS']:
            if not Shift.objects.filter(vet=self.vet,starts__lte=self.starts,ends__gte=self.ends).exists():
                raise ValidationError('El horario no está cubierto por un turno.')
            other = Appointment.objects.exclude(pk=self.pk).filter(status__in=['SCHEDULED','IN_PROGRESS'],starts__lt=self.ends,ends__gt=self.starts)
            if other.filter(vet=self.vet).exists(): raise ValidationError('El veterinario tiene otra cita en ese intervalo.')
            if other.filter(pet=self.pet).exists(): raise ValidationError('La mascota ya tiene una cita en ese intervalo.')
    def __str__(self): return f'#{self.pk} {self.pet.name} — {timezone.localtime(self.starts):%Y-%m-%d %H:%M}'

class Consultation(models.Model):
    appointment = models.OneToOneField(Appointment,on_delete=models.PROTECT,verbose_name='cita')
    diagnosis = models.TextField('diagnóstico')
    recommendations = models.TextField('recomendaciones')
    observations = models.TextField('observaciones',blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'Consulta #{self.pk} — {self.appointment.pet.name}'

class Medication(models.Model):
    consultation = models.ForeignKey(Consultation,on_delete=models.PROTECT,related_name='medications')
    name = models.CharField('medicamento',max_length=150)
    dose = models.CharField('dosis',max_length=100)
    frequency = models.CharField('frecuencia',max_length=100)
    duration = models.CharField('duración',max_length=100)

class Exam(models.Model):
    consultation = models.ForeignKey(Consultation,on_delete=models.PROTECT,verbose_name='consulta')
    kind = models.CharField('tipo',max_length=12,choices=[('BLOOD','Sangre'),('URINE','Orina'),('ULTRASOUND','Ecografía'),('XRAY','Radiografía')])
    service = models.ForeignKey(Service,on_delete=models.PROTECT,verbose_name='tarifa')
    results = models.TextField('resultado o borrador',blank=True)
    attachment = models.FileField('archivo PDF o imagen',upload_to='exams/%Y/%m/',blank=True,validators=[FileExtensionValidator(['pdf','jpg','jpeg','png'])])
    completed = models.BooleanField('resultado definitivo',default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        if self.service_id and (self.service.kind != 'EXAM' or not self.service.active): raise ValidationError('Selecciona una tarifa de examen activa.')
        if self.completed and not self.results and not self.attachment: raise ValidationError('Agrega texto o archivo para completar el resultado.')
    def __str__(self): return f'Examen #{self.pk} — {self.get_kind_display()}'

class Hospitalization(models.Model):
    consultation = models.ForeignKey(Consultation,on_delete=models.PROTECT,verbose_name='consulta')
    admitted_at = models.DateTimeField('ingreso',default=timezone.now)
    estimated_discharge = models.DateTimeField('salida estimada',null=True,blank=True)
    discharged_at = models.DateTimeField('alta',null=True,blank=True)
    reason = models.TextField('motivo')
    care = models.TextField('cuidados especiales')
    daily_rate = models.DecimalField('costo diario al cliente',**MONEY)
    service = models.ForeignKey(Service,on_delete=models.PROTECT,verbose_name='tarifa de hospitalización')
    summary = models.TextField('resumen de alta',blank=True)
    def clean(self):
        if self.discharged_at: positive_interval(self.admitted_at,self.discharged_at)
        if self.estimated_discharge: positive_interval(self.admitted_at,self.estimated_discharge)
        if self.admitted_at and self.admitted_at > timezone.now(): raise ValidationError('El ingreso no puede ser futuro.')
        if self.service_id and (self.service.kind != 'HOSPITAL' or not self.service.active): raise ValidationError('Selecciona una tarifa de hospitalización activa.')
    def __str__(self): return f'Hospitalización #{self.pk} — {self.consultation.appointment.pet.name}'

class HospitalNote(models.Model):
    hospitalization = models.ForeignKey(Hospitalization,on_delete=models.PROTECT,related_name='notes',verbose_name='hospitalización')
    author = models.ForeignKey(User,on_delete=models.PROTECT)
    text = models.TextField('observación médica')
    created_at = models.DateTimeField(auto_now_add=True)

class PlanConfig(models.Model):
    name = models.CharField('nombre',max_length=100,default='Plan Canitas')
    price = models.DecimalField('costo trimestral',default=Decimal('410000'),**MONEY)
    months = models.PositiveIntegerField('duración en meses',default=3,validators=[MinValueValidator(1),MaxValueValidator(24)])
    discount_percent = models.DecimalField('descuento porcentual',max_digits=5,decimal_places=2,default=10,validators=[MinValueValidator(0),MaxValueValidator(100)])
    # Cuotas por tipo de examen para todo el plan, no por mascota.
    included_exams = models.JSONField('exámenes incluidos por tipo',default=dict,blank=True)
    active = models.BooleanField('vigente para nuevas inscripciones',default=True)
    def clean(self):
        if not isinstance(self.included_exams,dict) or any(k not in ['BLOOD','URINE','ULTRASOUND','XRAY'] or type(v) is not int or v < 0 for k,v in self.included_exams.items()):
            raise ValidationError('Usa un objeto JSON con tipos de examen y cantidades enteras no negativas.')
    def __str__(self): return self.name

class Enrollment(models.Model):
    owner = models.ForeignKey(Customer,on_delete=models.PROTECT,verbose_name='propietario')
    pets = models.ManyToManyField(Pet,verbose_name='mascotas')
    config = models.ForeignKey(PlanConfig,on_delete=models.PROTECT,verbose_name='configuración')
    starts = models.DateField('inicio',default=timezone.localdate)
    ends = models.DateField('fin')
    price = models.DecimalField(**MONEY)
    discount_percent = models.DecimalField(max_digits=5,decimal_places=2)
    included_exams = models.JSONField(default=dict)
    alert_sent_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'Canitas #{self.pk} — {self.owner.name} hasta {self.ends}'

class Invoice(models.Model):
    owner = models.ForeignKey(Customer,on_delete=models.PROTECT)
    pet = models.ForeignKey(Pet,on_delete=models.PROTECT,null=True,blank=True)
    consultation = models.ForeignKey(Consultation,on_delete=models.PROTECT,null=True,blank=True)
    enrollment = models.OneToOneField(Enrollment,on_delete=models.PROTECT,null=True,blank=True)
    status = models.CharField(max_length=10,choices=[('PENDING','Pendiente'),('PARTIAL','Pago parcial'),('PAID','Pagada')],default='PENDING')
    issued_at = models.DateTimeField(default=timezone.now)
    @property
    def subtotal(self): return sum((i.subtotal for i in self.items.all()),ZERO)
    @property
    def discount(self): return sum((i.discount for i in self.items.all()),ZERO)
    @property
    def tax(self): return sum((i.tax for i in self.items.all()),ZERO)
    @property
    def total(self): return sum((i.total for i in self.items.all()),ZERO)
    @property
    def paid(self): return sum((p.amount for p in self.payments.all()),ZERO)
    @property
    def balance(self): return self.total-self.paid
    def __str__(self): return f'Factura #{self.pk} — {self.owner.name}'

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice,on_delete=models.PROTECT,related_name='items')
    service = models.ForeignKey(Service,on_delete=models.PROTECT)
    description = models.CharField(max_length=250)
    quantity = models.PositiveIntegerField(default=1,validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(**MONEY)
    unit_cost = models.DecimalField(**MONEY)
    tax_percent = models.DecimalField(max_digits=5,decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5,decimal_places=2,default=0)
    benefit_plan = models.ForeignKey(Enrollment,on_delete=models.PROTECT,null=True,blank=True)
    exam_kind = models.CharField(max_length=12,blank=True)
    included = models.BooleanField(default=False)
    @property
    def subtotal(self): return (self.unit_price*self.quantity).quantize(Decimal('.01'))
    @property
    def discount(self): return (self.subtotal*self.discount_percent/100).quantize(Decimal('.01'))
    @property
    def tax(self): return ((self.subtotal-self.discount)*self.tax_percent/100).quantize(Decimal('.01'))
    @property
    def total(self): return self.subtotal-self.discount+self.tax

class Payment(models.Model):
    invoice = models.ForeignKey(Invoice,on_delete=models.PROTECT,related_name='payments')
    amount = models.DecimalField(**MONEY)
    tendered = models.DecimalField(**MONEY)
    change = models.DecimalField(**MONEY)
    method = models.CharField(max_length=12,choices=[('CASH','Efectivo'),('CARD','Tarjeta'),('TRANSFER','Transferencia')])
    reference = models.CharField(max_length=150,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    key = models.UUIDField(unique=True) # Evita cobrar dos veces al reenviar un formulario.

class Audit(models.Model):
    actor = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True)
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=150,blank=True)
    ip = models.GenericIPAddressField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField(null=True,blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
