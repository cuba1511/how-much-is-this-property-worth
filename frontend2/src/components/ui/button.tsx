import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Button — driven by design tokens.
 *
 *   bg / fg            → action.{role}.{bg,fg}  (semantic tokens)
 *   shape (radius)     → radius.button (= 9999px pill)
 *   focus ring         → border.focus / shadow.focus
 *
 * Variants mirror the role surface in the token system:
 *   default     → action.primary
 *   destructive → action.destructive
 *   outline     → action.secondary (outline variant)
 *   secondary   → action.secondary
 *   ghost       → action.secondary (ghost)
 *   link        → fg.brand text link
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-page " +
    "disabled:pointer-events-none disabled:opacity-60 " +
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-card hover:bg-primary/90 active:bg-primary/80 focus-visible:ring-primary/40",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/80 focus-visible:ring-destructive/40",
        outline:
          "border border-line-brand text-brand bg-transparent hover:bg-surface-tint focus-visible:ring-primary/40",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/85 active:bg-secondary/75 focus-visible:ring-primary/40",
        ghost:
          "text-ink-secondary hover:bg-surface-muted hover:text-ink",
        link:
          "text-brand underline-offset-4 hover:underline",
      },
      size: {
        sm:   "h-9 px-4 text-text-md rounded-button",
        default: "h-10 px-6 text-text-md rounded-button",
        lg:   "h-12 px-8 text-text-lg rounded-button",
        icon: "h-10 w-10 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
