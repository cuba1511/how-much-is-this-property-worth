import { useTranslation } from 'react-i18next'
import { Clock } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import type { MarketTransaction } from '@/lib/types'
import { daysOnMarketBuckets } from '@/lib/results'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'

const chartConfig = {
  count: { label: '', color: 'hsl(var(--chart-1))' },
} satisfies ChartConfig

interface TimeOnMarketBlockProps {
  transactions: MarketTransaction[]
}

export function TimeOnMarketBlock({ transactions }: TimeOnMarketBlockProps) {
  const { t } = useTranslation()

  chartConfig.count.label = t('results.time.transactions')

  const daysArr = transactions
    .map((tx) => tx.days_on_market)
    .filter((d): d is number => d != null)

  if (daysArr.length < 3) return null

  const avgDays = Math.round(daysArr.reduce((a, b) => a + b, 0) / daysArr.length)
  const buckets = daysOnMarketBuckets(daysArr)

  return (
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      <h2 className="text-base font-semibold text-ink mb-md">{t('results.time.title')}</h2>

      <div className="flex items-center gap-sm mb-md">
        <div className="rounded-full bg-primary/10 p-2">
          <Clock className="h-5 w-5 text-primary" />
        </div>
        <p className="text-2xl font-bold text-ink">
          {t('results.time.avgDays', { count: avgDays })}
        </p>
      </div>

      <ChartContainer config={chartConfig} className="h-[160px] w-full mb-md">
        <BarChart data={buckets}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={11} />
          <YAxis tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Bar dataKey="count" fill="var(--color-count)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartContainer>

      <p className="text-xs text-ink-muted italic">{t('results.time.urgency')}</p>
    </div>
  )
}
