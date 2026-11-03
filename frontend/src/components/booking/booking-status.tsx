import type { BookingStatus } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

/**
 * Colour by what the status *means* to the reader, not by position in the state machine.
 *
 * Anything that needs attention (a reservation ticking toward expiry) reads as
 * secondary; anything that went wrong reads as destructive; the happy path is default.
 */
const TONE: Record<BookingStatus, "default" | "secondary" | "outline" | "destructive"> = {
  reserved: "secondary",
  confirmed: "default",
  paid: "default",
  completed: "outline",
  expired: "destructive",
  cancelled: "destructive",
  no_show: "destructive",
};

export function BookingStatusBadge({
  status,
  label,
  className,
}: {
  status: BookingStatus;
  label: string;
  className?: string;
}) {
  return (
    <Badge variant={TONE[status] ?? "secondary"} className={className}>
      {label}
    </Badge>
  );
}
