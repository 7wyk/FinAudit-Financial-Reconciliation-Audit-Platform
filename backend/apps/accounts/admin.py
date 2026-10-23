from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "first_name", "last_name", "is_active", "is_staff")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("-date_joined",)
