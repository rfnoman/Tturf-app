"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";

/**
 * A big +/− stepper.
 *
 * Scorers use this standing at the side of a pitch, on a phone, often in the dark — so
 * the targets are deliberately large and there is no keyboard involved. The number is
 * still editable by typing for the rare case of correcting a big total.
 */
export function ScoreStepper({
  label,
  value,
  onChange,
  min = 0,
  max = 999,
  step = 1,
  size = "lg",
  id,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  step?: number;
  size?: "lg" | "sm";
  id?: string;
}) {
  const clamp = (next: number) => Math.max(min, Math.min(max, next));
  const big = size === "lg";

  return (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size={big ? "icon-lg" : "icon-sm"}
        aria-label={`${label}: one fewer`}
        disabled={value <= min}
        onClick={() => onChange(clamp(value - step))}
      >
        <Minus aria-hidden />
      </Button>

      <input
        id={id}
        type="number"
        inputMode="numeric"
        aria-label={label}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(clamp(Number(event.target.value) || 0))}
        className={cn(
          "border-input bg-background rounded-lg border text-center font-mono tabular-nums",
          // The spinner arrows are redundant next to the buttons and shrink the target.
          "[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none",
          big ? "h-12 w-16 text-2xl font-semibold" : "h-8 w-12 text-sm",
        )}
      />

      <Button
        type="button"
        variant="outline"
        size={big ? "icon-lg" : "icon-sm"}
        aria-label={`${label}: one more`}
        disabled={value >= max}
        onClick={() => onChange(clamp(value + step))}
      >
        <Plus aria-hidden />
      </Button>
    </div>
  );
}
