import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import type { MarketTransactions } from '@/lib/types'
import { estimateSalePrice } from '@/lib/results'
import { formatPrice, formatPct } from './shared/formatters'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from '@/components/ui/chart'

const chartConfig = {
  asking_price: { label: '', color: 'hsl(var(--chart-1))' },
  closing_price: { label: '', color: 'hsl(var(--chart-2))' },
} satisfies ChartConfig

interface MarketRealityBlockProps {
  marketTransactions: MarketTransactions
  estimatedValue: number
  municipioName: string
}

export function MarketRealityBlock({ marketTransactions, estimatedValue, municipioName }: MarketRealityBlockProps) {
  const { t } = useTranslation()
  const { summary } = marketTransactions

  chartConfig.asking_price.label = t('results.market.asking')
  chartConfig.closing_price.label = t('results.market.closing')

  if (summary.asking_vs_closing_gap_pct == null) return null

  const salePrice = estimateSalePrice(estimatedValue, summary.asking_vs_closing_gap_pct)

  return (
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      <h2 className="text-base font-semibold text-ink mb-xs">{t('results.market.title')}</h2>
      <p className="text-lg font-bold text-ink mb-md">
        {t('results.market.headline', {
          municipio: municipioName,
          gap: summary.asking_vs_closing_gap_pct.toFixed(1),
        })}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-md mb-md">
        <div className="rounded-xl bg-surface-muted p-md">
          <p className="text-xs text-ink-secondary mb-1">{t('results.market.salePriceLabel')}</p>
          <p className="text-2xl font-bold text-ink">{formatPrice(salePrice)}</p>
        </div>
        <div className="rounded-xl bg-surface-muted p-md">
          <p className="text-xs text-ink-secondary mb-1">{t('results.market.marginLabel')}</p>
          <p className="text-2xl font-bold text-ink">{formatPct(summary.negotiation_margin_pct)}</p>
        </div>
      </div>

      {summary.chart_series.length > 0 && (
        <ChartContainer config={chartConfig} className="h-[240px] w-full">
          <BarChart data={summary.chart_series} barGap={2}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={11} />
            <YAxis
              tickLine={false}
              axisLine={false}
              fontSize={11}
              tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
            />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="asking_price" fill="var(--color-asking_price)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="closing_price" fill="var(--color-closing_price)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      )}
    </div>
  )
}
