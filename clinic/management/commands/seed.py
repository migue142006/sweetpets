from django.core.management.base import BaseCommand
from clinic.models import Service, PlanConfig
class Command(BaseCommand):
    help='Crea catálogo de ejemplo y parámetros Canitas, sin sobrescribir modificaciones.'
    def handle(self,*args,**kwargs):
        for name,kind,price,cost in [('Consulta general','CONSULT',60000,20000),('Spa','SPA',45000,15000),('Examen de sangre','EXAM',80000,35000),('Orina','EXAM',50000,20000),('Ecografía','EXAM',120000,45000),('Radiografía','EXAM',100000,40000),('Estadía hospitalaria','HOSPITAL',100000,45000),('Medicamento de ejemplo','PRODUCT',15000,7000)]:
            Service.objects.get_or_create(name=name,kind=kind,defaults={'price':price,'cost':cost,'tax_percent':0})
        PlanConfig.objects.get_or_create(name='Plan Canitas',defaults={'price':410000,'months':3,'discount_percent':10,'included_exams':{'BLOOD':1,'URINE':1}})
        self.stdout.write(self.style.SUCCESS('Catálogo creado. Los precios, impuestos y beneficios son ejemplos editables.'))
