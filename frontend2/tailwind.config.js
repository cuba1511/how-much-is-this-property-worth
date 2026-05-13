import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
/**
 * Theme driven entirely by design tokens defined in `src/styles/tokens.css`.
 * Hierarchy: primitives → semantic → components.
 *
 * Recommended utility names (forward-compat):
 *   Surfaces : bg-surface, bg-surface-muted, bg-surface-tint, bg-surface-elevated, bg-page
 *   Text     : text-ink, text-ink-secondary, text-ink-muted, text-ink-disabled,
 *              text-brand, text-brand-hover
 *   Borders  : border-line, border-line-strong, border-brand, border-error, border-success
 *   Status   : bg-success / bg-warning / bg-error (with -alt soft variants)
 *   Brand    : bg-brand (= bg-primary), text-brand
 *
 * shadcn class names (bg-card, text-foreground, bg-primary, etc.) keep working
 * because the underlying CSS vars are shared.
 */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    container: {
      center: true,
      padding: {
        DEFAULT: '1rem',
        sm: '1.5rem',
        lg: '2.5rem',
      },
      screens: {
        '2xl': '1280px',
      },
    },
    extend: {
      colors: {
        /* ----- shadcn-compatible aliases (use the new tokens) --------
         * `primary`, `secondary`, `destructive` are stored as space-separated
         * RGB channels in tokens.css so Tailwind's `bg-primary/40` opacity
         * modifier works correctly. */
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        primary: {
          DEFAULT: 'rgb(var(--primary-rgb) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground-rgb) / <alpha-value>)',
          hover: 'var(--color-action-primary-bg-hover)',
          active: 'var(--color-action-primary-bg-active)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary-rgb) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground-rgb) / <alpha-value>)',
          hover: 'var(--color-action-secondary-bg-hover)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--destructive-rgb) / <alpha-value>)',
          foreground: 'rgb(var(--destructive-foreground-rgb) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)',
        },

        /* ----- Semantic — surfaces ----------------------------------- */
        page: 'var(--color-bg-page)',
        surface: {
          DEFAULT: 'var(--color-bg-card)',
          muted: 'var(--color-bg-elevated-alt)',
          tint: 'var(--color-bg-primary-alt)',
          elevated: 'var(--color-bg-elevated)',
          disabled: 'var(--color-bg-disabled)',
        },

        /* ----- Semantic — foreground (text/icons) -------------------- */
        ink: {
          DEFAULT: 'var(--color-fg-primary)',
          secondary: 'var(--color-fg-secondary)',
          muted: 'var(--color-fg-tertiary)',
          disabled: 'var(--color-fg-disabled)',
          contrast: 'var(--color-fg-contrast)',
        },
        brand: {
          DEFAULT: 'var(--color-fg-brand)',
          hover: 'var(--color-fg-brand-hover)',
          disabled: 'var(--color-fg-brand-disabled)',
          50:  'var(--color-spaceblue-50)',
          100: 'var(--color-spaceblue-100)',
          200: 'var(--color-spaceblue-200)',
          300: 'var(--color-spaceblue-300)',
          400: 'var(--color-spaceblue-400)',
          500: 'var(--color-spaceblue-500)',
          600: 'var(--color-spaceblue-600)',
          700: 'var(--color-spaceblue-700)',
          800: 'var(--color-spaceblue-800)',
          900: 'var(--color-spaceblue-900)',
          950: 'var(--color-spaceblue-950)',
        },

        /* ----- Semantic — borders ----------------------------------- */
        line: {
          DEFAULT: 'var(--color-border-default)',
          subtle:  'var(--color-border-elevated)',
          strong:  'var(--color-border-secondary)',
          brand:   'var(--color-border-brand)',
          focus:   'var(--color-border-focus)',
          error:   'var(--color-border-error)',
          warning: 'var(--color-border-warning)',
          success: 'var(--color-border-success)',
        },

        /* ----- Semantic — status ------------------------------------ */
        success: {
          DEFAULT: 'var(--color-bg-success)',
          alt: 'var(--color-bg-success-alt)',
          fg:  'var(--color-fg-success)',
        },
        warning: {
          DEFAULT: 'var(--color-bg-warning)',
          alt: 'var(--color-bg-warning-alt)',
          fg:  'var(--color-fg-warning)',
        },
        info: {
          DEFAULT: 'var(--color-bg-primary-alt)',
          fg:  'var(--color-fg-info)',
        },
      },

      fontFamily: {
        sans: ['var(--font-family-sans)'],
        heading: ['var(--font-family-sans)'],
        body: ['var(--font-family-sans)'],
      },

      fontSize: {
        'text-xs':    ['var(--font-size-text-xs)',    { lineHeight: '12px', letterSpacing: '-0.01em' }],
        'text-sm':    ['var(--font-size-text-sm)',    { lineHeight: '16px', letterSpacing: '-0.015em' }],
        'text-md':    ['var(--font-size-text-md)',    { lineHeight: '20px', letterSpacing: '-0.02em' }],
        'text-lg':    ['var(--font-size-text-lg)',    { lineHeight: '24px', letterSpacing: '-0.025em' }],
        'header-sm':  ['var(--font-size-header-sm)',  { lineHeight: '26px', letterSpacing: '-0.03em' }],
        'header-md':  ['var(--font-size-header-md)',  { lineHeight: '28px', letterSpacing: '-0.03em' }],
        'header-lg':  ['var(--font-size-header-lg)',  { lineHeight: '32px', letterSpacing: '-0.04em' }],
        'header-xl':  ['var(--font-size-header-xl)',  { lineHeight: '38px', letterSpacing: '-0.04em' }],
        'header-2xl': ['var(--font-size-header-2xl)', { lineHeight: '44px', letterSpacing: '-0.05em' }],
        'header-3xl': ['var(--font-size-header-3xl)', { lineHeight: '58px', letterSpacing: '-0.06em' }],
      },

      spacing: {
        '0-5': 'var(--space-0-5)',
        xs:  'var(--space-1)',    /* 4 */
        sm:  'var(--space-2)',    /* 8 */
        md:  'var(--space-4)',    /* 16 */
        lg:  'var(--space-6)',    /* 24 */
        xl:  'var(--space-8)',    /* 32 */
        '2xl': 'var(--space-12)', /* 48 */
        '3xl': 'var(--space-16)', /* 64 */
        '4xl': 'var(--space-20)', /* 80 */
      },

      borderRadius: {
        none: 'var(--radius-0)',
        xs:   'var(--radius-1)',  /* 4  */
        sm:   'var(--radius-2)',  /* 8  */
        DEFAULT: 'var(--radius-2)',
        md:   'var(--radius-3)',  /* 12 */
        lg:   'var(--radius-4)',  /* 16 */
        xl:   'var(--radius-5)',  /* 20 */
        '2xl':'var(--radius-6)',  /* 24 */
        '3xl':'var(--radius-8)',  /* 32 */
        pill: 'var(--radius-full)',
        full: 'var(--radius-full)',

        /* Role-based */
        input:  'var(--radius-input)',
        button: 'var(--radius-button)',
        card:   'var(--radius-card)',
      },

      boxShadow: {
        'level-1': 'var(--shadow-level-1)',
        'level-2': 'var(--shadow-level-2)',
        'level-3': 'var(--shadow-level-3)',
        'level-4': 'var(--shadow-level-4)',
        card:      'var(--shadow-card)',
        lift:      'var(--shadow-lift)',
        focus:     'var(--shadow-focus)',
      },

      backdropBlur: {
        1: 'var(--blur-8)',
        2: 'var(--blur-12)',
        3: 'var(--blur-16)',
        4: 'var(--blur-24)',
        5: 'var(--blur-32)',
        6: 'var(--blur-40)',
        7: 'var(--blur-56)',
        8: 'var(--blur-64)',
      },

      transitionDuration: {
        fast: '150ms',
        DEFAULT: '200ms',
        normal: '250ms',
      },

      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to:   { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to:   { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up':   'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [animate],
}
