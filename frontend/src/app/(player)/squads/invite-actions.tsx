"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";

/** Accept or decline a squad invitation. */
export function SquadInviteActions({ inviteId }: { inviteId: string }) {
  const t = useTranslations("squads");
  const router = useRouter();
  const api = useApiClient();
  const [busy, setBusy] = useState(false);

  async function respond(accept: boolean) {
    setBusy(true);
    await api.POST("/api/v1/squad-invites/{invite_id}/respond", {
      params: { path: { invite_id: inviteId } },
      body: { approve: accept } as never,
    });
    setBusy(false);
    router.refresh();
  }

  return (
    <span className="flex gap-2">
      <Button size="xs" disabled={busy} onClick={() => respond(true)}>
        {t("accept")}
      </Button>
      <Button size="xs" variant="outline" disabled={busy} onClick={() => respond(false)}>
        {t("decline")}
      </Button>
    </span>
  );
}
