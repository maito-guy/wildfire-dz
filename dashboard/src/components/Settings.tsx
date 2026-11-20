import { useState } from "react";
import { getOperatorToken, setOperatorToken } from "../operatorToken";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

// The operator token is sent as X-Operator-Token on every write call.
export function Settings({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [token, setToken] = useState(getOperatorToken);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="font-display text-[21px] font-bold">Settings</SheetTitle>
          <SheetDescription>Kept in this browser only.</SheetDescription>
        </SheetHeader>
        <label className="flex flex-col gap-1.5 px-4">
          <span className="label-mono">Operator token</span>
          <Input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              setOperatorToken(e.target.value);
            }}
          />
          <span className="text-xs text-muted-foreground">Sent with Send alert, Cancel, Approve, Reject and Reset.</span>
        </label>
      </SheetContent>
    </Sheet>
  );
}
