import uuid
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction, connection
from django.db.models import Q
from django.http import JsonResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import *
from .forms import *
from . import services as ops
from .reports import report_data, pdf_response, excel_response
from .services import billed_days

def roles(*allowed):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            ops.allow(request.user,*allowed)
            return view(request,*args,**kwargs)
        return wrapped
    return decorate

MODULES={
 'customers':(Customer,CustomerForm,'Clientes',['ADMIN','RECEPTION']),
 'pets':(Pet,PetForm,'Mascotas',['ADMIN','RECEPTION']),
 'services':(Service,ServiceForm,'Servicios y productos',['ADMIN']),
 'shifts':(Shift,ShiftForm,'Turnos',['ADMIN']),
 'appointments':(Appointment,AppointmentForm,'Citas',['ADMIN','RECEPTION']),
 'consultations':(Consultation,ConsultationForm,'Consultas',['ADMIN','VET']),
 'exams':(Exam,ExamForm,'Exámenes',['ADMIN','VET']),
 'hospitalizations':(Hospitalization,HospitalForm,'Hospitalizaciones',['ADMIN','VET']),
 'plans':(PlanConfig,PlanForm,'Configuración Canitas',['ADMIN']),
 'enrollments':(Enrollment,EnrollmentForm,'Inscripciones Canitas',['ADMIN','RECEPTION']),
 'invoices':(Invoice,None,'Facturas',['ADMIN','RECEPTION']),
 'users':(User,UserForm,'Usuarios',['ADMIN']),
}

def module(key):
    if key not in MODULES: raise PermissionDenied
    return MODULES[key]

def scoped(request,key,qs):
    if request.user.role=='VET':
        if key=='appointments': qs=qs.filter(vet=request.user)
        elif key=='consultations': qs=qs.filter(appointment__vet=request.user)
        elif key in ['exams','hospitalizations']: qs=qs.filter(consultation__appointment__vet=request.user)
    return qs

@login_required
def home(request):
    today=timezone.localdate()
    agenda=Appointment.objects.filter(starts__date=today).select_related('pet','vet','service')
    agenda=scoped(request,'appointments',agenda)
    expiring=Enrollment.objects.filter(ends__gt=today,ends__lte=today+timedelta(days=15),invoice__status='PAID').select_related('owner') if request.user.role!='VET' else []
    return render(request,'clinic/home.html',{'agenda':agenda,'expiring':expiring})

def health(request):
    try:
        with connection.cursor() as c: c.execute('SELECT 1')
        return JsonResponse({'status':'ok'})
    except Exception: return JsonResponse({'status':'unavailable'},status=503)

@login_required
def listing(request,key):
    model,_,title,allowed=module(key)
    readable=allowed+(['VET'] if key in ['pets','customers','appointments','shifts'] else ['RECEPTION'] if key in ['consultations','exams','hospitalizations'] else [])
    ops.allow(request.user,*readable)
    qs=scoped(request,key,model.objects.all())
    q=request.GET.get('q','').strip()
    if q:
        names=[f.name for f in model._meta.fields if isinstance(f,(models.CharField,models.TextField)) and f.name not in ['password']]
        query=Q()
        for name in names: query|=Q(**{f'{name}__icontains':q})
        if q.isdigit(): query|=Q(pk=int(q))
        qs=qs.filter(query)
    day=request.GET.get('day')
    if day and key in ['appointments','shifts']:
        try: qs=qs.filter(starts__date=date.fromisoformat(day))
        except ValueError: messages.error(request,'Fecha inválida')
    from django.core.paginator import Paginator
    page=Paginator(qs.order_by('-pk'),25).get_page(request.GET.get('page'))
    rows=[]
    for obj in page:
        if key=='customers': fields=[obj.name,obj.email,obj.phone,'Activo' if obj.active else 'Inactivo']
        elif key=='pets': fields=[obj.name,obj.owner.name,obj.get_species_display(),obj.birth_date,'Hospitalizada' if Hospitalization.objects.filter(consultation__appointment__pet=obj,discharged_at__isnull=True).exists() else 'Ambulatoria']
        elif key=='appointments': fields=[obj.pet.name,str(obj.vet),timezone.localtime(obj.starts).strftime('%d/%m/%Y %H:%M'),obj.get_status_display()]
        elif key=='invoices': fields=[obj.owner.name,obj.get_status_display(),f'Total ${obj.total}',f'Saldo ${obj.balance}']
        elif key=='users': fields=[obj.username,obj.email,obj.get_role_display(),'Activo' if obj.is_active else 'Inactivo']
        elif key=='hospitalizations': fields=[str(obj),'Alta' if obj.discharged_at else 'Hospitalizada',obj.admitted_at]
        elif key=='enrollments': fields=[str(obj),', '.join(p.name for p in obj.pets.all()),'Pagado' if obj.invoice.status=='PAID' else 'Pendiente de pago']
        else: fields=[str(obj)]
        rows.append((obj,fields))
    return render(request,'clinic/list.html',{'key':key,'title':title,'rows':rows,'page':page,'can_write':request.user.role in allowed or request.user.is_superuser,'can_create':key!='invoices','q':q})

@login_required
def edit(request,key,pk=None):
    model,form_class,title,allowed=module(key); ops.allow(request.user,*allowed)
    if not form_class: raise PermissionDenied
    obj=get_object_or_404(scoped(request,key,model.objects.all()),pk=pk) if pk else None
    if pk and key in ['consultations','hospitalizations','enrollments']: raise PermissionDenied
    if key=='users' and obj and obj.is_superuser: raise PermissionDenied
    kwargs={}
    if key in ['consultations','exams','hospitalizations']: kwargs['actor']=request.user
    if obj: kwargs['instance']=obj
    if key=='users' and obj: form_class=UserEditForm
    form=form_class(request.POST if request.method=="POST" else None,request.FILES or None,**kwargs)
    medications=MedicationFormSet(request.POST if request.method=="POST" else None,queryset=Medication.objects.none(),prefix='meds') if key=='consultations' else None
    if request.method=='POST' and form.is_valid() and (medications is None or medications.is_valid()):
        try:
            with transaction.atomic():
                if key=='enrollments': result=ops.enroll(request.user,**form.cleaned_data)
                else:
                    result=form.save(commit=False)
                    if key=='shifts': ops.save_shift(request.user,result)
                    elif key=='appointments': ops.save_appointment(request.user,result)
                    elif key=='consultations':
                        meds=[{k:f.cleaned_data[k] for k in ['name','dose','frequency','duration']} for f in medications if f.cleaned_data]
                        ops.finish_consultation(request.user,result,meds)
                    elif key=='exams': ops.save_exam(request.user,result)
                    elif key=='hospitalizations': ops.admit(request.user,result)
                    else:
                        if key=='users' and obj:
                            if obj.pk==request.user.pk and (not result.is_active or result.role!='ADMIN'):
                                raise ValidationError('No puedes desactivar tu propia cuenta o quitarte el rol administrador.')
                            if form.cleaned_data['new_password']: result.set_password(form.cleaned_data['new_password'])
                        result.full_clean(); result.save(); ops.audit(request.user,'guardar '+key,result)
            messages.success(request,'Registro guardado.')
            return redirect('listing',key=key)
        except ValidationError as e: form.add_error(None,e)
        except IntegrityError: form.add_error(None,'Conflicto de datos. Verifica duplicados o disponibilidad y vuelve a intentar.')
    return render(request,'clinic/form.html',{'title':title,'form':form,'medications':medications})

@login_required
def action(request,key,pk,operation):
    obj=get_object_or_404(module(key)[0],pk=pk)
    form=None; title=operation
    allowed_map={'cancel':['ADMIN','RECEPTION'],'spa':['ADMIN','RECEPTION'],'pay':['ADMIN','RECEPTION'],'item':['ADMIN','RECEPTION'],'second-pet':['ADMIN','RECEPTION'],'discharge':['ADMIN','VET'],'note':['ADMIN','VET']}
    if operation not in allowed_map: raise PermissionDenied
    ops.allow(request.user,*allowed_map[operation])
    if operation in ['discharge','note']:
        if key!='hospitalizations': raise PermissionDenied
        ops.clinical(request.user,obj.consultation)
    if operation in ['cancel','spa'] and key!='appointments': raise PermissionDenied
    if operation in ['pay','item'] and key!='invoices': raise PermissionDenied
    if operation=='second-pet' and key!='enrollments': raise PermissionDenied
    form_classes={'pay':PaymentForm,'item':ExtraItemForm,'second-pet':SecondPetForm,'discharge':DischargeForm,'note':NoteForm}
    cls=form_classes.get(operation,forms.Form)
    initial={'key':uuid.uuid4(),'amount':obj.balance,'tendered':obj.balance} if operation=='pay' else {}
    form=cls(request.POST if request.method=="POST" else None,initial=initial)
    if operation=='second-pet': form.fields['pet'].queryset=Pet.objects.filter(owner=obj.owner,active=True).exclude(enrollment=obj)
    if request.method=='POST' and form.is_valid():
        try:
            if operation=='cancel': ops.cancel_appointment(request.user,pk)
            elif operation=='spa': ops.finish_spa(request.user,pk)
            elif operation=='pay': ops.pay(request.user,pk,**form.cleaned_data)
            elif operation=='item':
                with transaction.atomic():
                    ops.add_item(obj,**form.cleaned_data); ops.audit(request.user,'agregar línea a factura',obj)
            elif operation=='second-pet': ops.add_plan_pet(request.user,pk,**form.cleaned_data)
            elif operation=='discharge': ops.discharge(request.user,pk,**form.cleaned_data)
            elif operation=='note': ops.add_hospital_note(request.user,obj,**form.cleaned_data)
            messages.success(request,'Operación completada.')
            return redirect('listing',key=key)
        except ValidationError as e: form.add_error(None,e)
        except IntegrityError: form.add_error(None,'Conflicto de datos. Revisa la operación antes de reenviarla.')
    return render(request,'clinic/form.html',{'title':f'{operation} — {obj}','form':form})

@login_required
def history(request,pk):
    pet=get_object_or_404(Pet,pk=pk)
    consultations=Consultation.objects.filter(appointment__pet=pet).select_related('appointment').prefetch_related('medications').order_by('-created_at')
    exams=Exam.objects.filter(consultation__appointment__pet=pet).order_by('-created_at')
    hospitals=Hospitalization.objects.filter(consultation__appointment__pet=pet).prefetch_related('notes').order_by('-admitted_at')
    for h in hospitals:
        h.current_days=billed_days(h.admitted_at,h.discharged_at or timezone.now())
        h.current_cost=h.current_days*h.daily_rate
    return render(request,'clinic/history.html',{'pet':pet,'consultations':consultations,'exams':exams,'hospitals':hospitals,'now':timezone.now()})

@login_required
def attachment(request,pk):
    e=get_object_or_404(Exam,pk=pk)
    if not e.attachment: from django.http import Http404; raise Http404
    # Archivos privados: no hay ruta pública /media/.
    return FileResponse(e.attachment.open('rb'),as_attachment=True,filename=Path(e.attachment.name).name)

@roles('ADMIN','RECEPTION')
def invoice_pdf(request,pk):
    inv=get_object_or_404(Invoice,pk=pk)
    rows=[['Concepto','Cantidad','Precio','Descuento','Impuesto','Total']]
    rows += [[i.description,i.quantity,i.unit_price,i.discount,i.tax,i.total] for i in inv.items.all()]
    paragraphs=[f'Cliente: {inv.owner.name}. Correo: {inv.owner.email}',f'Fecha: {timezone.localtime(inv.issued_at):%d/%m/%Y %H:%M}. Estado: {inv.get_status_display()}',f'Subtotal: ${inv.subtotal}. Descuento: ${inv.discount}. Impuestos: ${inv.tax}. Total: ${inv.total}',f'Pagado: ${inv.paid}. Saldo: ${inv.balance}','Comprobante interno. No es factura electrónica validada por la DIAN.']
    paragraphs += [f'Pago {p.created_at:%d/%m/%Y}: {p.get_method_display()}, abono ${p.amount}, recibido ${p.tendered}, cambio ${p.change}, referencia {p.reference}' for p in inv.payments.all()]
    return pdf_response(f'factura-{pk}.pdf',f'SweetPets comprobante {pk}',paragraphs,rows)

@roles('ADMIN')
def reports(request):
    today=timezone.localdate(); start_text=request.GET.get('start',today.replace(day=1).isoformat()); end_text=request.GET.get('end',today.isoformat())
    kind=request.GET.get('kind','')
    try:
        start,end=date.fromisoformat(start_text),date.fromisoformat(end_text)
        if end<start or kind not in ['',*dict(Service.KINDS)]: raise ValueError()
    except ValueError:
        messages.error(request,'Filtros inválidos. Usa fechas válidas y un servicio de la lista.'); return redirect('reports')
    data=report_data(start,end,kind)
    fmt=request.GET.get('format')
    if fmt=='xlsx': return excel_response(data)
    if fmt=='pdf': return pdf_response('reporte.pdf','Reporte SweetPets',[f'Periodo {start} a {end}',f'Recaudo ${data["income"]}; ventas netas ${data["net_sales"]}; costos directos ${data["direct_cost"]}; margen estimado ${data["margin"]}'],[['Servicio','Unidades','Mascotas','%','Facturado']]+data['rows'])
    return render(request,'clinic/reports.html',{'data':data,'start':start_text,'end':end_text,'kind':kind,'kinds':Service.KINDS,'chart':{'months':{k:float(v) for k,v in data['months'].items()},'services':[[r[0],r[1]] for r in data['rows']]}})

@roles('ADMIN','RECEPTION')
def availability(request):
    day=request.GET.get('day',timezone.localdate().isoformat())
    try: parsed=date.fromisoformat(day)
    except ValueError: messages.error(request,'Fecha inválida'); return redirect('availability')
    from datetime import datetime,time
    start=timezone.make_aware(datetime.combine(parsed,time.min)); end=start+timedelta(days=1)
    shifts=Shift.objects.filter(starts__lt=end,ends__gt=start).select_related('vet')
    appointments=Appointment.objects.filter(starts__lt=end,ends__gt=start,status__in=['SCHEDULED','IN_PROGRESS']).select_related('vet','pet')
    return render(request,'clinic/availability.html',{'day':day,'shifts':shifts,'appointments':appointments})

@login_required
def calendar(request):
    import calendar as cal
    today=timezone.localdate()
    month=request.GET.get('month',today.strftime('%Y-%m'))
    try:
        first=date.fromisoformat(month+'-01')
    except ValueError:
        messages.error(request,'Mes inválido'); return redirect('calendar')
    shifts=Shift.objects.filter(starts__year=first.year,starts__month=first.month).select_related('vet')
    if request.user.role=='VET': shifts=shifts.filter(vet=request.user)
    grouped={}
    for shift in shifts:
        grouped.setdefault(timezone.localtime(shift.starts).day,[]).append(shift)
    weeks=[[(day,grouped.get(day,[])) for day in week] for week in cal.Calendar(firstweekday=0).monthdayscalendar(first.year,first.month)]
    return render(request,'clinic/calendar.html',{'weeks':weeks,'month':month})
