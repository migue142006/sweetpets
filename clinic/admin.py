from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Audit, Notification
@admin.register(User)
class SweetUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets+(( 'SweetPets',{'fields':('role','failed_attempts','locked_until')}),)
    add_fieldsets=UserAdmin.add_fieldsets+(( 'SweetPets',{'fields':('email','first_name','last_name','role')}),)
    list_display=('username','email','role','is_active')
    readonly_fields=('failed_attempts','locked_until')
    def has_module_permission(self,request): return request.user.is_superuser
    def has_view_permission(self,request,obj=None): return request.user.is_superuser
    def has_add_permission(self,request): return request.user.is_superuser
    def has_change_permission(self,request,obj=None): return request.user.is_superuser
    def has_delete_permission(self,request,obj=None): return False
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
admin.site.register(Audit,ReadOnlyAdmin)
admin.site.register(Notification,ReadOnlyAdmin)
admin.site.site_header='SweetPets — administración técnica'
