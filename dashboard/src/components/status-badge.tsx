// Status in words, never colour alone (DESIGN.md §7.1). Preventive (risk-today flags) is an ink outline.
import { cva } from "class-variance-authority";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusBadge = cva(
  "rounded-md px-2 py-1 font-mono text-[10.5px] font-semibold uppercase tracking-[0.06em] border-transparent",
  {
    variants: {
      status: {
        leave_now: "bg-fire text-fire-foreground",
        get_ready: "bg-flame text-flame-foreground",
        safe: "bg-transparent border-border text-safe",
        update: "bg-primary text-primary-foreground",
        cancel: "bg-charcoal text-white dark:text-foreground",
        preventive: "bg-transparent border-ink text-ink",
      },
    },
  },
);

export type BadgeStatus = "leave_now" | "get_ready" | "safe" | "update" | "cancel" | "preventive";

const LABEL: Record<BadgeStatus, string> = {
  leave_now: "Leave now",
  get_ready: "Get ready",
  safe: "Safe",
  update: "Update",
  cancel: "Cancelled",
  preventive: "Risk today",
};

export function StatusBadge({ status, className }: { status: BadgeStatus; className?: string }) {
  return <Badge className={cn(statusBadge({ status }), className)}>{LABEL[status]}</Badge>;
}
