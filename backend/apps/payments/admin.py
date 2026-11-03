from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("booking", "method", "amount", "status", "collected_by", "collected_at")
    list_filter = ("method", "status")
    search_fields = ("reference", "booking__id")
    autocomplete_fields = ("booking", "collected_by")
    readonly_fields = ("created_at", "updated_at")
