// Toasts (DESIGN.md §8): ink background, green check, top-centre. Light theme only (DESIGN.md §3.1).
import { CheckCircle, Info, SpinnerGap, Warning, XCircle } from "@phosphor-icons/react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

const Toaster = (props: ToasterProps) => (
  <Sonner
    theme="light"
    position="top-center"
    className="toaster group"
    icons={{
      success: <CheckCircle weight="fill" className="size-4 text-ok" />,
      info: <Info className="size-4" />,
      warning: <Warning className="size-4 text-flame" />,
      error: <XCircle weight="fill" className="size-4 text-fire" />,
      loading: <SpinnerGap className="size-4 animate-spin" />,
    }}
    toastOptions={{
      classNames: {
        toast: "!bg-ink !text-white !border-0 !shadow-toast font-sans text-sm font-semibold",
        description: "!text-white/70",
      },
    }}
    {...props}
  />
)

export { Toaster }
