"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { MatchDetail, SquadMember } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/** Surface the API's own message — "this match is full" is the useful part. */
function describe(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const parts: string[] = [];
  for (const [field, value] of Object.entries(error as Record<string, unknown>)) {
    const message = Array.isArray(value) ? value.join(" ") : String(value);
    parts.push(
      ["detail", "match", "status", "player"].includes(field) ? message : `${field}: ${message}`,
    );
  }
  return parts.length > 0 ? parts.join("\n") : null;
}

/**
 * Everything a reader can do on a match page, gated by who they are.
 *
 * The API decides what is permitted; this decides what to show — and shows the API's
 * refusal when the two disagree, rather than silently doing nothing.
 */
export function MatchActions({
  match,
  invitable,
}: {
  match: MatchDetail;
  invitable: SquadMember[];
}) {
  const t = useTranslations("matchPage");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [addToSquad, setAddToSquad] = useState(false);
  const [invitee, setInvitee] = useState("");

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(describe(apiError) ?? t("failed"));
      return false;
    }
    router.refresh();
    return true;
  }

  const matchPath = { path: { id: match.id } };

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="text-destructive text-sm whitespace-pre-line">
          {error}
        </p>
      )}

      {/* --- the reader's own position in the match --------------------------- */}
      {!match.is_on_roster && match.my_invite_id && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("youAreInvited")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy === "invite"}
              onClick={() =>
                run("invite", () =>
                  api.POST("/api/v1/match-invites/{invite_id}/respond", {
                    params: { path: { invite_id: match.my_invite_id! } },
                    body: { approve: true } as never,
                  }),
                )
              }
            >
              {t("acceptInvite")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "invite"}
              onClick={() =>
                run("invite", () =>
                  api.POST("/api/v1/match-invites/{invite_id}/respond", {
                    params: { path: { invite_id: match.my_invite_id! } },
                    body: { approve: false } as never,
                  }),
                )
              }
            >
              {t("declineInvite")}
            </Button>
          </CardContent>
        </Card>
      )}

      {!match.is_on_roster && !match.my_invite_id && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            {match.can_request ? (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="request-message" className="text-xs">
                    {t("requestMessage")}
                  </Label>
                  <Input
                    id="request-message"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder={t("requestPlaceholder")}
                    maxLength={300}
                  />
                </div>
                <Button
                  size="sm"
                  className="self-start"
                  disabled={busy === "request"}
                  onClick={() =>
                    run("request", () =>
                      api.POST("/api/v1/matches/{id}/request", {
                        params: matchPath,
                        body: { message } as never,
                      }),
                    )
                  }
                >
                  {t("requestToJoin")}
                </Button>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">
                {match.cannot_request_reason || t("cannotJoin")}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {match.is_on_roster && !match.is_organiser && (
        <Button
          size="sm"
          variant="outline"
          className="self-start"
          disabled={busy === "leave"}
          onClick={() =>
            run("leave", () =>
              api.POST("/api/v1/matches/{id}/leave", { params: matchPath, body: {} as never }),
            )
          }
        >
          {t("leaveMatch")}
        </Button>
      )}

      {/* --- the organiser's decision queues ----------------------------------- */}
      {match.is_organiser && match.pending_requests.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {t("pendingRequests", { count: match.pending_requests.length })}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {match.squad && (
              <div className="flex items-center gap-2">
                <Switch id="add-to-squad" checked={addToSquad} onCheckedChange={setAddToSquad} />
                <Label htmlFor="add-to-squad" className="text-xs font-normal">
                  {t("alsoAddToSquad")}
                </Label>
              </div>
            )}

            {match.pending_requests.map((request) => (
              <div
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="block font-medium">{request.player_name}</span>
                  {request.message && (
                    <span className="text-muted-foreground block text-xs">{request.message}</span>
                  )}
                </span>
                <span className="flex gap-2">
                  <Button
                    size="xs"
                    disabled={busy === request.id}
                    onClick={() =>
                      run(request.id, () =>
                        api.POST("/api/v1/join-requests/{request_id}/decide", {
                          params: { path: { request_id: request.id } },
                          body: { approve: true, add_to_squad: addToSquad } as never,
                        }),
                      )
                    }
                  >
                    {t("approve")}
                  </Button>
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={busy === request.id}
                    onClick={() =>
                      run(request.id, () =>
                        api.POST("/api/v1/join-requests/{request_id}/decide", {
                          params: { path: { request_id: request.id } },
                          body: { approve: false } as never,
                        }),
                      )
                    }
                  >
                    {t("decline")}
                  </Button>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {match.is_organiser && match.live_invites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("invitations")}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("proposalsHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {match.live_invites.map((invite) => (
              <div
                key={invite.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="block font-medium">{invite.invited_player_name}</span>
                  <span className="text-muted-foreground block text-xs">
                    {invite.status === "proposed"
                      ? t("proposedBy", { name: invite.invited_by_name || "A member" })
                      : t("awaitingPlayer")}
                  </span>
                </span>
                {invite.status === "proposed" && (
                  <span className="flex gap-2">
                    <Button
                      size="xs"
                      disabled={busy === invite.id}
                      onClick={() =>
                        run(invite.id, () =>
                          api.POST("/api/v1/match-invites/{invite_id}/decide", {
                            params: { path: { invite_id: invite.id } },
                            body: { approve: true } as never,
                          }),
                        )
                      }
                    >
                      {t("approve")}
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={busy === invite.id}
                      onClick={() =>
                        run(invite.id, () =>
                          api.POST("/api/v1/match-invites/{invite_id}/decide", {
                            params: { path: { invite_id: invite.id } },
                            body: { approve: false } as never,
                          }),
                        )
                      }
                    >
                      {t("reject")}
                    </Button>
                  </span>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* --- inviting ----------------------------------------------------------- */}
      {invitable.length > 0 && match.needed > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("invitePlayer")}</CardTitle>
            <p className="text-muted-foreground text-xs">
              {match.is_organiser ? t("inviteHintOrganiser") : t("inviteHintMember")}
            </p>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="invitee" className="text-xs">
                {t("player")}
              </Label>
              <select
                id="invitee"
                value={invitee}
                onChange={(event) => setInvitee(event.target.value)}
                className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
              >
                <option value="">{t("choosePlayer")}</option>
                {invitable.map((member) => (
                  <option key={member.id} value={member.profile_id ?? ""}>
                    {member.name}
                  </option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              disabled={!invitee || busy === "invite-player"}
              onClick={async () => {
                const ok = await run("invite-player", () =>
                  api.POST("/api/v1/matches/{id}/invite", {
                    params: matchPath,
                    body: { player_id: invitee } as never,
                  }),
                );
                if (ok) setInvitee("");
              }}
            >
              {t("sendInvite")}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
