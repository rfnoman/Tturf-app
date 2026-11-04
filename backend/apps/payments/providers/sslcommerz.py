"""SSLCommerz (DECISIONS D8), against the current v4 API.

Endpoints, from SSLCommerz's own integration docs:

* session   ``POST .../gwprocess/v4/api.php``
* validate  ``GET  .../validator/api/validationserverAPI.php``
* refund    ``GET  .../validator/api/merchantTransIDvalidationAPI.php``

**The security story, in one place.** The gateway sends the player back to a success URL
*and* posts an IPN to the server. Both are attacker-controllable: anyone can POST to the
callback, and the redirect can be typed into a browser. So neither is believed. What
decides the outcome is a server-to-server call to the validation API with the `val_id`,
followed by three checks on the answer:

1. the status is `VALID` or `VALIDATED`,
2. the transaction id is **ours**, for **this** payment,
3. the amount matches what we asked for, to the paisa.

Anything else is a failure with a reason in the log and nothing moved. Card numbers are
never stored — SSLCommerz only returns a masked one, and even that stays out of our logs.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from .base import PaymentProvider, ProviderError, RefundResult, StartedPayment, ValidationResult

logger = logging.getLogger(__name__)

SANDBOX_BASE = "https://sandbox.sslcommerz.com"
LIVE_BASE = "https://securepay.sslcommerz.com"

#: SSLCommerz answers a validated transaction with one of these.
PAID_STATUSES = {"VALID", "VALIDATED"}
TIMEOUT_SECONDS = 20


class SSLCommerzProvider(PaymentProvider):
    name = "sslcommerz"

    def __init__(
        self, *, store_id: str = "", store_password: str = "", sandbox: bool | None = None
    ):
        self.store_id = store_id or settings.SSLCOMMERZ_STORE_ID
        self.store_password = store_password or settings.SSLCOMMERZ_STORE_PASSWORD
        self.sandbox = settings.SSLCOMMERZ_SANDBOX if sandbox is None else sandbox

    @property
    def base_url(self) -> str:
        """Live, sandbox, or — in development only — a local stand-in.

        `SSLCOMMERZ_BASE_URL` exists so the whole payment path can be walked in a
        browser without sandbox credentials. It is empty everywhere else, and setting it
        in production would be as visible as it sounds.
        """
        override = getattr(settings, "SSLCOMMERZ_BASE_URL", "")
        if override:
            return override.rstrip("/")
        return SANDBOX_BASE if self.sandbox else LIVE_BASE

    @property
    def is_configured(self) -> bool:
        return bool(self.store_id and self.store_password)

    # -- starting -----------------------------------------------------------
    def start(self, *, payment, return_urls: dict) -> StartedPayment:
        if not self.is_configured:
            raise ProviderError("SSLCommerz is not configured on this server.")

        target = payment.target
        player = getattr(target, "booked_by", None) or getattr(target, "player", None)
        profile = getattr(player, "player_profile", None)

        payload = {
            "store_id": self.store_id,
            "store_passwd": self.store_password,
            "total_amount": f"{payment.amount:.2f}",
            "currency": "BDT",
            "tran_id": payment.provider_txn_id,
            "success_url": return_urls["success"],
            "fail_url": return_urls["fail"],
            "cancel_url": return_urls["cancel"],
            "ipn_url": return_urls["ipn"],
            "cus_name": (profile.name if profile else None)
            or getattr(player, "full_name", "")
            or "TurfApp player",
            "cus_email": getattr(player, "email", "") or "player@turfapp.local",
            "cus_phone": getattr(player, "phone", "") or "01700000000",
            "cus_add1": "Dhaka",
            "cus_city": "Dhaka",
            "cus_postcode": "1200",
            "cus_country": "Bangladesh",
            "shipping_method": "NO",
            "product_name": self._describe(payment),
            "product_category": "sports",
            "product_profile": "general",
            # Echoed back on every callback, so a reply can be tied to a row without
            # trusting anything else in it.
            "value_a": str(payment.id),
            "value_b": payment.kind,
        }

        data = self._post(f"{self.base_url}/gwprocess/v4/api.php", payload)
        if str(data.get("status", "")).upper() != "SUCCESS":
            raise ProviderError(
                f"SSLCommerz refused the session: {data.get('failedreason') or data.get('status')}"
            )

        return StartedPayment(
            redirect_url=data.get("GatewayPageURL", ""),
            reference=payment.provider_txn_id,
            raw=self._safe(data),
        )

    # -- validating ---------------------------------------------------------
    def validate(self, *, payment, callback: dict) -> ValidationResult:
        """Ask SSLCommerz directly, then check the answer against our own row."""
        val_id = (callback or {}).get("val_id", "")
        if not val_id:
            return ValidationResult(is_paid=False, reason="No val_id in the callback.")
        if not self.is_configured:
            raise ProviderError("SSLCommerz is not configured on this server.")

        data = self._get(
            f"{self.base_url}/validator/api/validationserverAPI.php",
            {
                "val_id": val_id,
                "store_id": self.store_id,
                "store_passwd": self.store_password,
                "format": "json",
            },
        )

        status = str(data.get("status", "")).upper()
        reference = str(data.get("tran_id", ""))
        amount = self._decimal(data.get("amount"))
        currency = str(data.get("currency_type") or data.get("currency") or "BDT").upper()
        result = {
            "amount": amount,
            "currency": currency,
            "reference": reference,
            "bank_reference": str(data.get("bank_tran_id", "")),
            "status": status,
            "raw": self._safe(data),
        }

        if status not in PAID_STATUSES:
            return ValidationResult(is_paid=False, reason=f"Gateway said {status}.", **result)

        # The three checks that make this safe. Each is its own failure, because
        # "mismatched amount" and "wrong transaction" mean very different things when
        # somebody is reading the log at 2am.
        if reference != payment.provider_txn_id:
            logger.warning(
                "Callback for a different transaction",
                extra={"payment": str(payment.id), "expected": payment.provider_txn_id},
            )
            return ValidationResult(
                is_paid=False, reason="That transaction belongs to another payment.", **result
            )

        if amount is None or amount != payment.amount:
            logger.warning(
                "Callback amount does not match",
                extra={"payment": str(payment.id), "expected": str(payment.amount)},
            )
            return ValidationResult(is_paid=False, reason="The amount does not match.", **result)

        if currency != "BDT":
            return ValidationResult(is_paid=False, reason="Unexpected currency.", **result)

        return ValidationResult(is_paid=True, **result)

    # -- refunding ----------------------------------------------------------
    def refund(self, *, payment, amount: Decimal, reason: str) -> RefundResult:
        if not self.is_configured:
            raise ProviderError("SSLCommerz is not configured on this server.")
        if not payment.bank_txn_id:
            return RefundResult(
                is_accepted=False, reason="No bank transaction id to refund against."
            )

        data = self._get(
            f"{self.base_url}/validator/api/merchantTransIDvalidationAPI.php",
            {
                "bank_tran_id": payment.bank_txn_id,
                "refund_amount": f"{amount:.2f}",
                "refund_remarks": reason[:255] or "Refund",
                "refe_id": str(payment.id),
                "store_id": self.store_id,
                "store_passwd": self.store_password,
                "format": "json",
            },
        )

        api_connect = str(data.get("APIConnect", "")).upper()
        status = str(data.get("status", "")).lower()
        accepted = api_connect == "DONE" and status in {"success", "processing"}

        return RefundResult(
            is_accepted=accepted,
            reference=str(data.get("refund_ref_id", "")),
            status=status or api_connect.lower(),
            raw=self._safe(data),
            reason="" if accepted else str(data.get("errorReason") or api_connect),
        )

    # -- plumbing -----------------------------------------------------------
    def _post(self, url: str, payload: dict) -> dict:
        try:
            response = requests.post(url, data=payload, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except ValueError as exc:
            raise ProviderError("SSLCommerz did not return JSON.") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Could not reach SSLCommerz: {exc}") from exc

    def _get(self, url: str, params: dict) -> dict:
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except ValueError as exc:
            raise ProviderError("SSLCommerz did not return JSON.") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Could not reach SSLCommerz: {exc}") from exc

    @staticmethod
    def _decimal(value) -> Decimal | None:
        try:
            return Decimal(str(value))
        except TypeError, InvalidOperation:
            return None

    @staticmethod
    def _describe(payment) -> str:
        target = payment.target
        if getattr(target, "ground", None) is not None:
            return f"Booking at {target.ground.turf.name}"[:255]
        return "TurfApp order"

    @staticmethod
    def _safe(data: dict) -> dict:
        """Everything the gateway said, minus what must never be stored.

        Our own credentials come back in some responses, and a masked card number is
        still card data. Neither belongs in a database row or a log line.
        """
        drop = {"store_id", "store_passwd", "card_no", "verify_sign", "verify_key"}
        return {key: value for key, value in (data or {}).items() if key not in drop}
