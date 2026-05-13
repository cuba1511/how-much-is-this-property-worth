import { useTranslation } from 'react-i18next'
import { ExternalLink, CheckCircle2 } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, ReferenceLine } from 'recharts'
import type { SearchMetadata, ValuationStats, Listing } from '@/lib/types'
import { priceDistribution } from '@/lib/results'
import { formatPrice } from './shared/formatters'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'

const chartConfig = {
  count: { label: 'Count', color: 'hsl(var(--chart-3))' },
} satisfies ChartConfig

interface HowWeGotThereBlockProps {
  searchMetadata: SearchMetadata
  searchUrl: string
  stats: ValuationStats
  listings: Listing[]
}

export function HowWeGotThereBlock({ searchMetadata, searchUrl, stats, listings }: HowWeGotThereBlockProps) {
  const { t } = useTranslation()
  const { stages } = searchMetadata

  if (stages.length === 0) return null

  const distribution = priceDistribution(listings)

  return (
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      <h2 className="text-base font-semibold text-ink mb-md">{t('results.howWeGotThere.title')}</h2>

      {/* Stage timeline */}
      <div className="flex flex-wrap gap-sm mb-md">
        {stages.map((stage, i) => {
          const isFinal = stage.name === searchMetadata.final_stage
          return (
            <div
              key={i}
              className={`flex flex-col gap-1 rounded-xl border p-sm text-xs ${
                isFinal
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                  : 'border-line bg-surface-muted'
              }`}
            >
              <div className="flex items-center gap-1 font-semibold text-ink">
                {isFinal && <CheckCircle2 className="h-3.5 w-3.5 text-primary" />}
                {t(`results.stages.${stage.name}`, { defaultValue: stage.label })}
              </div>
              <span className="text-ink-muted">
                {t('results.howWeGotThere.listings', { count: stage.listings_found })}
              </span>
              {stage.area_min != null && stage.area_max != null && (
                <span className="text-ink-muted">
                  {t('results.howWeGotThere.areaRange', { min: stage.area_min, max: stage.area_max })}
                </span>
              )}
              <span className="text-ink-muted">
                {t('results.howWeGotThere.duration', { ms: stage.duration_ms })}
              </span>
            </div>
          )
        })}
      </div>

      {/* Price distribution chart */}
      {distribution.length > 0 && (
        <div className="mb-md">
          <p className="text-xs font-medium text-ink-secondary mb-sm">{t('results.howWeGotThere.priceDistribution')}</p>
          <ChartContainer config={chartConfig} className="h-[180px] w-full">
            <BarChart data={distribution}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={10} />
              <YAxis tickLine={false} axisLine={false} fontSize={10} allowDecimals={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={[4, 4, 0, 0]} />
              {stats.estimated_value != null && (
                <ReferenceLine
                  x={distribution.find((b) => stats.estimated_value! >= b.rangeMin && stats.estimated_value! <= b.rangeMax)?.label}
                  stroke="hsl(var(--chart-2))"
                  strokeDasharray="4 4"
                  label={{ value: t('results.howWeGotThere.estimated'), position: 'top', fontSize: 10 }}
                />
              )}
            </BarChart>
          </ChartContainer>
        </div>
      )}

      <a
        href={searchUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
      >
        {t('results.howWeGotThere.viewOnIdealista')}
        <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </div>
  )
}
