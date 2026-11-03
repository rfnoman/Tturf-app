"use client";

import { useFormatter } from "next-intl";

/**
 * A booking's slot, in Dhaka time.
 *
 * The time zone is pinned rather than left to the browser: a player checking their
 * booking from abroad still needs to know when to be at the turf in Dhaka.
 */
export function BookingTime({
  start,
  end,
  withDate = true,
}: {
  start: string;
  end: string;
  withDate?: boolean;
}) {
  const format = useFormatter();
  const options = { timeZone: "Asia/Dhaka", hour: "2-digit", minute: "2-digit" } as const;

  return (
    <span className="font-mono tabular-nums">
      {withDate &&
        `${format.dateTime(new Date(start), {
          timeZone: "Asia/Dhaka",
          weekday: "short",
          day: "numeric",
          month: "short",
        })} · `}
      {format.dateTime(new Date(start), options)}–{format.dateTime(new Date(end), options)}
    </span>
  );
}

/** A single moment in Dhaka time — a timeline entry, not a slot. */
export function DhakaMoment({ at }: { at: string }) {
  const format = useFormatter();
  return (
    <span className="font-mono tabular-nums">
      {format.dateTime(new Date(at), {
        timeZone: "Asia/Dhaka",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })}
    </span>
  );
}

/** A countdown to a reservation's expiry, for the staff confirmation queue. */
export function ExpiresIn({ at }: { at: string }) {
  const format = useFormatter();
  return <span>{format.relativeTime(new Date(at))}</span>;
}
