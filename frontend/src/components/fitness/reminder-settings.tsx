"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { ReminderPreference } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const SWITCHES = ["match_day", "hydration", "recovery", "order_cutoff", "weekly_recap"] as const;

/**
 * What the app is allowed to interrupt a player about.
 *
 * Push is deliberately last and opt-in: the browser prompt is a one-shot — refuse it
 * once and it never asks again — so it is only requested when somebody taps for it.
 */
export function ReminderSettings({
  preference,
  vapidPublicKey,
}: {
  preference: ReminderPreference;
  vapidPublicKey: string;
}) {
  const t = useTranslations("reminders");
  const api = useApiClient();

  const [current, setCurrent] = useState(preference);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pushNote, setPushNote] = useState<string | null>(null);

  async function save(changes: Partial<ReminderPreference>) {
    // Optimistic: a switch that does not move until the server answers feels broken,
    // and the only thing at stake is a preference. A failure puts it back.
    const previous = current;
    setCurrent((value) => ({ ...value, ...changes }));
    setBusy(true);
    setError(null);

    const { data, error: apiError } = await api.PATCH("/api/v1/me/reminders", {
      body: changes as never,
    });
    setBusy(false);

    if (apiError || !data) {
      setCurrent(previous);
      setError(t("failed"));
      return;
    }
    setCurrent(data);
  }

  async function enablePush() {
    setPushNote(null);
    if (!vapidPublicKey) {
      setPushNote(t("pushUnavailable"));
      return;
    }
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setPushNote(t("pushUnsupported"));
      return;
    }

    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushNote(t("pushRefused"));
        return;
      }

      const registration = await navigator.serviceWorker.register("/sw.js");
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      });

      const raw = subscription.toJSON();
      const { error: apiError } = await api.POST("/api/v1/me/push", {
        body: {
          endpoint: raw.endpoint,
          p256dh: raw.keys?.p256dh,
          auth: raw.keys?.auth,
          user_agent: navigator.userAgent.slice(0, 200),
        } as never,
      });
      if (apiError) {
        setPushNote(t("pushFailed"));
        return;
      }
      setCurrent((value) => ({ ...value, push_enabled: true }));
      setPushNote(t("pushOn"));
    } catch {
      setPushNote(t("pushFailed"));
    }
  }

  return (
    <Card data-testid="reminder-settings">
      <CardHeader>
        <CardTitle className="text-sm">{t("heading")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("body")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        <ul className="flex flex-col gap-2">
          {SWITCHES.map((key) => (
            <li key={key} className="flex items-center justify-between gap-3">
              <label htmlFor={`reminder-${key}`} className="text-sm">
                {t("kind", { kind: key })}
              </label>
              <input
                id={`reminder-${key}`}
                type="checkbox"
                checked={Boolean(current[key])}
                disabled={busy}
                onChange={(event) => save({ [key]: event.target.checked })}
                className="size-4"
              />
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-end gap-3 border-t pt-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="quiet-from" className="text-xs">
              {t("quietFrom")}
            </Label>
            <Input
              id="quiet-from"
              type="time"
              value={(current.quiet_from ?? "22:00").slice(0, 5)}
              disabled={busy}
              onChange={(event) => save({ quiet_from: `${event.target.value}:00` })}
              className="w-28"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="quiet-until" className="text-xs">
              {t("quietUntil")}
            </Label>
            <Input
              id="quiet-until"
              type="time"
              value={(current.quiet_until ?? "07:00").slice(0, 5)}
              disabled={busy}
              onChange={(event) => save({ quiet_until: `${event.target.value}:00` })}
              className="w-28"
            />
          </div>
          <p className="text-muted-foreground w-full text-xs">{t("quietHint")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t pt-4">
          {current.push_enabled ? (
            <span className="text-sm">{t("pushAlreadyOn")}</span>
          ) : (
            <Button size="sm" variant="outline" onClick={enablePush}>
              {t("enablePush")}
            </Button>
          )}
          {pushNote && (
            <span role="status" className="text-muted-foreground text-sm">
              {pushNote}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * The VAPID key travels as URL-safe base64; `subscribe` wants raw bytes.
 *
 * Typed as `ArrayBuffer` rather than `Uint8Array`: TypeScript's `BufferSource` will not
 * accept a view whose buffer might be shared, and the underlying buffer here never is.
 */
function urlBase64ToUint8Array(base64: string): ArrayBuffer {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}
