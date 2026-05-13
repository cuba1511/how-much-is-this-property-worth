import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

interface FloatingChatProps {
  leadName?: string
  delayMs?: number
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-typing-dot" />
      <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-typing-dot [animation-delay:0.2s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-typing-dot [animation-delay:0.4s]" />
    </div>
  )
}

export function FloatingChat({ leadName, delayMs = 5000 }: FloatingChatProps) {
  const { t } = useTranslation()
  const [showMessage, setShowMessage] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const t1 = setTimeout(() => setOpen(true), delayMs)
    const t2 = setTimeout(() => setShowMessage(true), delayMs + 1800)

    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [delayMs])

  const nameSegment = leadName ? `, ${leadName.split(' ')[0]}` : ''

  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex flex-col items-end gap-3 max-w-[360px]">
      {open ? (
        <div className="animate-chat-slide-in rounded-2xl border border-line bg-surface shadow-lift w-full">
          {/* Header */}
          <div className="flex items-center gap-3 border-b border-line px-4 py-3">
            <div className="relative shrink-0">
              <img
                src="/agent-tifany.jpg"
                alt={t('chat.agentName')}
                className="h-10 w-10 rounded-full object-cover"
              />
              <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-surface bg-emerald-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink leading-tight">{t('chat.agentName')}</p>
              <p className="text-xs text-ink-muted">{t('chat.agentRole')}</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full p-1 text-ink-muted transition hover:bg-surface-muted hover:text-ink"
              aria-label={t('chat.close')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div className="px-4 py-3">
            {!showMessage ? (
              <TypingIndicator />
            ) : (
              <div className="animate-chat-bubble-in">
                <div className="rounded-xl rounded-tl-sm bg-surface-tint px-4 py-3">
                  <p className="text-sm text-ink leading-relaxed">
                    {t('chat.greeting', { name: nameSegment })}
                  </p>
                </div>

                <a
                  href="https://wa.me/34600000000"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary mt-3 w-full text-sm py-2.5"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
                  </svg>
                  {t('chat.cta')}
                </a>
              </div>
            )}
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="animate-chat-slide-in relative h-14 w-14 rounded-full shadow-lift transition hover:scale-105 hover:shadow-xl"
          aria-label="Chat"
        >
          <img
            src="/agent-tifany.jpg"
            alt={t('chat.agentName')}
            className="h-full w-full rounded-full object-cover ring-2 ring-primary"
          />
          <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-emerald-400 animate-pulse" />
        </button>
      )}
    </div>
  )
}
