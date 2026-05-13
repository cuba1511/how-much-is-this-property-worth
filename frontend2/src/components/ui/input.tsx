import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Input — semantic tokens for shell, border, and state.
 *   bg/border/fg ........ components.input.* → semantic
 *   radius .............. components.input.radius (8px)
 *   focus state ......... border-brand + brand/20 ring
 *   error state ......... aria-invalid="true"  → border-error + error/20 ring
 *   disabled state ...... bg-elevated-alt + fg-disabled
 */
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-input border border-line bg-page px-3 py-2",
          "text-text-md text-ink placeholder:text-ink-muted",
          "transition-colors duration-fast",
          "file:border-0 file:bg-transparent file:text-text-sm file:font-medium file:text-foreground",
          "focus-visible:outline-none focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-primary/20",
          "aria-[invalid=true]:border-line-error aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-destructive/20",
          "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-disabled",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
