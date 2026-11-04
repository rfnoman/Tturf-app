from django.contrib import admin

from .models import CommissionPlan, LedgerEntry, Payment, Payout, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "method", "kind", "amount", "status", "booking", "order")
    list_filter = ("method", "status", "kind")
    search_fields = ("provider_txn_id", "bank_txn_id", "reference")
    raw_id_fields = ("booking", "order", "collected_by")
    # The gateway's reply is evidence; editing it would destroy the only record of what
    # was actually said.
    readonly_fields = ("provider_txn_id", "bank_txn_id", "gateway_status", "raw_response")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("created_at", "payment", "amount", "status", "settled_at")
    list_filter = ("status",)
    raw_id_fields = ("payment", "requested_by")
    readonly_fields = ("provider_ref", "raw_response")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("occurred_on", "account", "turf", "type", "amount", "note")
    list_filter = ("account", "type", "turf")
    search_fields = ("note",)
    raw_id_fields = ("payment", "refund", "payout", "turf")
    readonly_fields = tuple(field.name for field in LedgerEntry._meta.fields)

    def has_add_permission(self, request) -> bool:
        # Entries are written in balanced sets by `post_entries`; a hand-added line
        # would break the one invariant the ledger has.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CommissionPlan)
class CommissionPlanAdmin(admin.ModelAdmin):
    list_display = ("turf", "booking_percent", "sales_percent", "monthly_subscription", "is_active")
    list_filter = ("is_active",)
    raw_id_fields = ("turf",)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("turf", "period_start", "period_end", "amount", "status", "sent_at")
    list_filter = ("status", "turf")
    raw_id_fields = ("turf", "sent_by")
    readonly_fields = ("amount",)
