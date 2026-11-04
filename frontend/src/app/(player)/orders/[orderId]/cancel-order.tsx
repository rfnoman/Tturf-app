"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** A player may call it off until somebody has packed it. */
export function CancelOrder({ orderId }: { orderId: string }) {
  const t = useTranslations("orders");
  const router = useRouter();
  const api = useApiClient();

  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-wrap items-end gap-2 border-t pt-4">
      {error && (
        <p role="alert" className="text-destructive w-full text-sm">
          {error}
        </p>
      )}
      <div className="flex min-w-48 flex-1 flex-col gap-1.5">
        <Label htmlFor="cancel-reason" className="text-xs">
          {t("cancelReason")}
        </Label>
        <Input
          id="cancel-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t("cancelPlaceholder")}
          maxLength={200}
        />
      </div>
      <Button
        size="sm"
        variant="destructive"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          const { error: apiError } = await api.POST("/api/v1/orders/{order_id}/cancel", {
            params: { path: { order_id: orderId } },
            body: { reason } as never,
          });
          setBusy(false);
          if (apiError) {
            setError(t("cancelFailed"));
            return;
          }
          router.refresh();
        }}
      >
        {t("cancelOrder")}
      </Button>
    </div>
  );
}
