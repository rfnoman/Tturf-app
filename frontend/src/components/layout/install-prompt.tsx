"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

/** The event Chrome fires when it would be willing to install the app. */
type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISSED = "turfapp:install-dismissed";

/**
 * An "add to home screen" offer, shown once.
 *
 * The browser only fires `beforeinstallprompt` when it has decided the app is
 * installable and is not installed already, so there is nothing to feature-detect: no
 * event, no banner. Safari never fires it at all, which is correct behaviour here —
 * iOS installs from the share sheet and a banner telling somebody to do that is the kind
 * of thing people install an app to get away from.
 *
 * Dismissal sticks, in `localStorage`. A prompt that comes back every visit is an advert.
 */
export function InstallPrompt() {
  const t = useTranslations("install");
  const [event, setEvent] = useState<InstallEvent | null>(null);

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISSED)) return;
    } catch {
      // Private windows and locked-down browsers throw on access. Showing the banner is
      // the right fallback — worst case it reappears next visit.
    }

    const onPrompt = (incoming: Event) => {
      // Chrome shows its own mini-infobar unless this is called.
      incoming.preventDefault();
      setEvent(incoming as InstallEvent);
    };

    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  if (!event) return null;

  const close = () => {
    setEvent(null);
    try {
      localStorage.setItem(DISMISSED, "1");
    } catch {
      // Not worth failing over: the banner is gone for this visit either way.
    }
  };

  return (
    <div
      className="bg-muted/60 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm"
      data-testid="install-prompt"
    >
      <span>{t("body")}</span>
      <span className="flex gap-2">
        <Button
          size="sm"
          onClick={async () => {
            await event.prompt();
            // Whatever they chose, the event is spent — it cannot be prompted twice.
            close();
          }}
        >
          {t("install")}
        </Button>
        <Button size="sm" variant="ghost" onClick={close}>
          {t("notNow")}
        </Button>
      </span>
    </div>
  );
}
