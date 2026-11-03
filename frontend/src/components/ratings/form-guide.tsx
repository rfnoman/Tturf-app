import { cn } from "cn";

/** The last few results, newest first (DOMAIN §3). */
export function FormGuide({ form, label }: { form: string[]; label: string }) {
  if (form.length === 0) return null;

  return (
    <span className="flex items-center gap-1" aria-label={label}>
      {form.map((result, index) => (
        <span
          key={`${result}-${index}`}
          title={result}
          className={cn(
            "flex size-5 items-center justify-center rounded text-[10px] font-bold text-white",
            result === "win" && "bg-emerald-600",
            result === "loss" && "bg-destructive",
            result === "draw" && "bg-muted-foreground",
          )}
        >
          {result === "win" ? "W" : result === "loss" ? "L" : "D"}
        </span>
      ))}
    </span>
  );
}
