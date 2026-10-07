import uuid
from io import BytesIO
from PIL import Image
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import *

class DateInput(forms.DateInput):
    input_type='date'
class DateTimeInput(forms.DateTimeInput):
    input_type='datetime-local'
    def __init__(self,**kwargs): super().__init__(format='%Y-%m-%dT%H:%M',**kwargs)
class BaseForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for f in self.fields.values():
            if isinstance(f,forms.DateTimeField):
                f.widget=DateTimeInput(); f.input_formats=['%Y-%m-%dT%H:%M']
            elif isinstance(f,forms.DateField): f.widget=DateInput()
        for name,f in self.fields.items():
            if isinstance(f,forms.ModelChoiceField):
                model=f.queryset.model
                if model in [Pet,Customer,Service,PlanConfig]: f.queryset=f.queryset.filter(active=True)

class CustomerForm(BaseForm):
    class Meta: model=Customer; fields=['name','address','phone','email','active']
class PetForm(BaseForm):
    class Meta: model=Pet; fields=['owner','name','species','breed','birth_date','weight','notes','active']
class ServiceForm(BaseForm):
    class Meta: model=Service; fields=['name','kind','price','cost','tax_percent','active']
class ShiftForm(BaseForm):
    class Meta: model=Shift; fields=['vet','starts','ends','kind']
class AppointmentForm(BaseForm):
    class Meta: model=Appointment; fields=['pet','vet','service','starts','ends','reason']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['service'].queryset=Service.objects.filter(active=True,kind__in=['CONSULT','SPA'])
class ConsultationForm(BaseForm):
    class Meta: model=Consultation; fields=['appointment','diagnosis','recommendations','observations']
    def __init__(self,*args,actor=None,**kwargs):
        super().__init__(*args,**kwargs)
        qs=Appointment.objects.filter(status__in=['SCHEDULED','IN_PROGRESS'],service__kind='CONSULT')
        if actor and actor.role=='VET': qs=qs.filter(vet=actor)
        self.fields['appointment'].queryset=qs
MedicationFormSet=forms.modelformset_factory(Medication,fields=['name','dose','frequency','duration'],extra=3,can_delete=False)
class ExamForm(BaseForm):
    class Meta: model=Exam; fields=['consultation','kind','service','results','attachment','completed']
    def __init__(self,*args,actor=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['service'].queryset=Service.objects.filter(active=True,kind='EXAM')
        if actor and actor.role=='VET': self.fields['consultation'].queryset=Consultation.objects.filter(appointment__vet=actor)
        if self.instance.pk:
            for field in ['consultation','kind','service']: self.fields[field].disabled=True
    def clean_attachment(self):
        f=self.cleaned_data.get('attachment')
        if not f or not hasattr(f,'content_type'): return f
        if f.size > 5*1024*1024: raise ValidationError('Archivo máximo de 5 MB.')
        data=f.read(); f.seek(0)
        if f.name.lower().endswith('.pdf'):
            if not data.startswith(b'%PDF-'): raise ValidationError('El archivo no es un PDF.')
        else:
            try:
                image=Image.open(BytesIO(data)); image.verify()
                if image.format not in ['PNG','JPEG']: raise ValueError()
            except Exception: raise ValidationError('Imagen PNG o JPEG inválida.')
        f.name=f'{uuid.uuid4().hex}.{f.name.rsplit(".",1)[-1].lower()}'
        return f
class HospitalForm(BaseForm):
    class Meta: model=Hospitalization; fields=['consultation','admitted_at','estimated_discharge','reason','care','service','daily_rate']
    def __init__(self,*args,actor=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['service'].queryset=Service.objects.filter(active=True,kind='HOSPITAL')
        if actor and actor.role=='VET': self.fields['consultation'].queryset=Consultation.objects.filter(appointment__vet=actor)
class PlanForm(BaseForm):
    class Meta: model=PlanConfig; fields=['name','price','months','discount_percent','included_exams','active']
class EnrollmentForm(forms.Form):
    owner=forms.ModelChoiceField(Customer.objects.filter(active=True),label='Propietario')
    pets=forms.ModelMultipleChoiceField(Pet.objects.filter(active=True),label='Una o dos mascotas del mismo dueño')
    config=forms.ModelChoiceField(PlanConfig.objects.filter(active=True),label='Configuración Canitas')
class PaymentForm(forms.Form):
    amount=forms.DecimalField(label='Abono aplicado al saldo',max_digits=12,decimal_places=2,min_value=Decimal('0.01'))
    tendered=forms.DecimalField(label='Dinero recibido',max_digits=12,decimal_places=2,min_value=Decimal('0.01'))
    method=forms.ChoiceField(label='Método',choices=Payment._meta.get_field('method').choices)
    reference=forms.CharField(label='Referencia',required=False,max_length=150)
    key=forms.UUIDField(widget=forms.HiddenInput)
class DischargeForm(forms.Form):
    end=forms.DateTimeField(label='Fecha y hora del alta',widget=DateTimeInput(),input_formats=['%Y-%m-%dT%H:%M'])
    summary=forms.CharField(label='Resumen de alta',widget=forms.Textarea)
class NoteForm(forms.Form):
    text=forms.CharField(label='Observación',widget=forms.Textarea)
class SecondPetForm(forms.Form):
    pet=forms.ModelChoiceField(Pet.objects.filter(active=True),label='Segunda mascota')
class ExtraItemForm(forms.Form):
    service=forms.ModelChoiceField(Service.objects.filter(active=True).exclude(kind='PLAN'),label='Servicio o producto')
    quantity=forms.IntegerField(label='Cantidad',min_value=1,max_value=10000)
class UserForm(UserCreationForm):
    class Meta:
        model=User
        fields=['username','email','first_name','last_name','role']
class UserEditForm(forms.ModelForm):
    new_password=forms.CharField(label='Nueva contraseña opcional',required=False,widget=forms.PasswordInput)
    class Meta: model=User; fields=['email','first_name','last_name','role','is_active']
    def clean_new_password(self):
        value=self.cleaned_data.get('new_password')
        if value: validate_password(value,self.instance)
        return value
