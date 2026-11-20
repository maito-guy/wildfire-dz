// Toasts (DESIGN.md §8): strongest-contrast background, green check, top-centre. Follows the theme.
import { CheckCircle, Info, SpinnerGap, Warning, XCircle } from "@phosphor-icons/react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

const Toaster = (props: ToasterProps) => (
  <Sonner
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
        toast: "!bg-primary !text-primary-foreground !border-0 !shadow-toast font-sans text-sm font-semibold",
        description: "!text-primary-foreground/70",
      },
    }}
    {...props}
  />
)

export { Toaster }
