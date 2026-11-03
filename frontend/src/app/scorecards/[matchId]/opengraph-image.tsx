import { ImageResponse } from "next/og";

import { createPublicApiClient } from "@/lib/api/client";

export const alt = "Match scorecard";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The preview card for a shared scorecard link.
 *
 * Drawn here rather than screenshotted: WhatsApp and Messenger fetch this once and show
 * it at thumbnail size, so it is the score, the teams and the turf — nothing smaller than
 * that survives the scaling. Plain inline styles only; `next/og` supports no CSS files.
 */
export default async function Image({ params }: { params: Promise<{ matchId: string }> }) {
  // Async like every other `params` in Next 16, image routes included.
  const { matchId } = await params;
  const api = createPublicApiClient();
  const { data } = await api.GET("/api/v1/public/matches/{match_id}/scorecard", {
    params: { path: { match_id: matchId } },
  });

  const teamA = data?.teams.find((team) => team.side === "A")?.display_name ?? "Team A";
  const teamB = data?.teams.find((team) => team.side === "B")?.display_name ?? "Team B";
  const when = data
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Dhaka",
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(data.played_at))
    : "";

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #052e16 0%, #064e3b 60%, #065f46 100%)",
        color: "white",
        fontFamily: "sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: 30,
          letterSpacing: 8,
          opacity: 0.75,
          textTransform: "uppercase",
        }}
      >
        {data ? `${data.sport} · ${data.turf_name}` : "TurfApp"}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 48, marginTop: 36 }}>
        <Side name={teamA} score={data?.team_a_score ?? 0} won={data?.result === "A"} />
        <div style={{ display: "flex", fontSize: 72, opacity: 0.5 }}>–</div>
        <Side name={teamB} score={data?.team_b_score ?? 0} won={data?.result === "B"} />
      </div>

      {/* One flat string per node, and no glyph outside the bundled font: a star or a
          tick sends Satori off to download a font, and that failing fails the whole
          image. Satori also wants an explicit display on anything with two children. */}
      <div style={{ display: "flex", gap: 28, marginTop: 44, fontSize: 28, opacity: 0.85 }}>
        <div style={{ display: "flex" }}>{when}</div>
        {data?.motm_name ? (
          <div style={{ display: "flex" }}>{`MOTM: ${data.motm_name}`}</div>
        ) : null}
        {data?.verified_by_staff ? <div style={{ display: "flex" }}>Verified by turf</div> : null}
      </div>
    </div>,
    size,
  );
}

function Side({ name, score, won }: { name: string; score: number; won: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        width: 380,
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: 160,
          fontWeight: 700,
          color: won ? "#4ade80" : "white",
        }}
      >
        {String(score)}
      </div>
      <div style={{ display: "flex", fontSize: 34, opacity: 0.9, textAlign: "center" }}>{name}</div>
    </div>
  );
}
