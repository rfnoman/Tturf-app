from django.urls import path

from .views import (
    AdminBookingRefundView,
    AdminFinanceView,
    AdminPayoutSendView,
    AdminPayoutView,
    AdminRefundListView,
    BookingRefundQuoteView,
    MyPaymentsView,
    PaymentDetailView,
    PaymentIpnView,
    StartPaymentView,
    TurfFinanceView,
    TurfPayoutListView,
    TurfStatementCsvView,
)

urlpatterns = [
    path("payments/start", StartPaymentView.as_view(), name="payment-start"),
    path("payments/<uuid:payment_id>", PaymentDetailView.as_view(), name="payment-detail"),
    # Unauthenticated, and safe because it decides nothing on its own.
    path("payments/ipn/<str:provider>", PaymentIpnView.as_view(), name="payment-ipn"),
    path("me/payments", MyPaymentsView.as_view(), name="my-payments"),
    path(
        "bookings/<uuid:booking_id>/refund-quote",
        BookingRefundQuoteView.as_view(),
        name="refund-quote",
    ),
    path("me/turfs/<slug:slug>/finance", TurfFinanceView.as_view(), name="turf-finance"),
    path(
        "me/turfs/<slug:slug>/finance.csv",
        TurfStatementCsvView.as_view(),
        name="turf-finance-csv",
    ),
    path("me/turfs/<slug:slug>/payouts", TurfPayoutListView.as_view(), name="turf-payouts"),
    path("admin/finance", AdminFinanceView.as_view(), name="admin-finance"),
    path("admin/refunds", AdminRefundListView.as_view(), name="admin-refunds"),
    path(
        "admin/bookings/<uuid:booking_id>/refund",
        AdminBookingRefundView.as_view(),
        name="admin-refund-booking",
    ),
    path("admin/payouts", AdminPayoutView.as_view(), name="admin-payouts"),
    path(
        "admin/payouts/<uuid:payout_id>/send",
        AdminPayoutSendView.as_view(),
        name="admin-payout-send",
    ),
]
