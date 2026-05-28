import animate from "tailwindcss-animate"

/** @type {import('tailwindcss').Config} */
/**
 * Semantic aliases are mapped to the Figma-exported design tokens in
 * `frontend/src/index.css` (`design-tokensLast version`).
 */
export default {
  darkMode: ["class"],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          light: 'var(--ds-color-bg-primary-alt)',
          dark: 'var(--ds-color-fg-brand-hover)',
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          light: '#ff7a40',
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        highlight: {
          DEFAULT: '#ea4ac0',
          foreground: '#ffffff',
        },
        surface: {
          DEFAULT: 'var(--ds-color-bg-card)',
          muted: 'var(--ds-color-bg-page)',
          tint: 'var(--ds-color-bg-primary-alt)',
          elevated: 'var(--ds-color-bg-elevated-alt)',
        },
        ink: {
          DEFAULT: 'var(--ds-color-fg-primary)',
          secondary: 'var(--ds-color-fg-secondary)',
          muted: 'var(--ds-color-fg-tertiary)',
          success: 'var(--ds-color-fg-success)',
        },
        line: {
          DEFAULT: 'var(--ds-color-border-elevated)',
          strong: 'var(--ds-color-border-default)',
          brand: 'var(--ds-color-border-brand)',
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
      },
      fontFamily: {
        heading: ['Inter', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      spacing: {
        xs: '4px',
        sm: '8px',
        md: '16px',
        lg: '24px',
        xl: '32px',
        '2xl': '48px',
        '3xl': '64px',
      },
      boxShadow: {
        card: 'var(--ds-shadow-level-1)',
        lift: 'var(--ds-shadow-level-2)',
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: 'var(--ds-radius-card)',
        '2xl': 'var(--ds-radius-card)',
        pill: 'var(--ds-radius-button)',
      },
      transitionDuration: {
        DEFAULT: '200ms',
        fast: '150ms',
        normal: '250ms',
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "chat-slide-in": {
          from: { opacity: "0", transform: "translateY(16px) scale(0.95)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "chat-bubble-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "typing-dot": {
          "0%, 60%, 100%": { opacity: "0.3", transform: "translateY(0)" },
          "30%": { opacity: "1", transform: "translateY(-3px)" },
        },
        "progress-indeterminate": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "chat-slide-in": "chat-slide-in 0.4s ease-out forwards",
        "chat-bubble-in": "chat-bubble-in 0.3s ease-out forwards",
        "typing-dot": "typing-dot 1.2s ease-in-out infinite",
        "progress-indeterminate": "progress-indeterminate 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [animate],
}
