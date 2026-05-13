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
  count: { label: '', color: 'var(--chart-1)' },
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
    <div className="card-surface p-lg">
      <h2 className="text-header-sm mb-md">{t('results.time.title')}</h2>

      <div className="mb-md flex items-center gap-sm">
        <div className="rounded-full bg-primary/10 p-sm">
          <Clock className="h-5 w-5 text-brand" />
        </div>
        <p className="text-header-lg font-semibold text-ink">
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

      <p className="text-text-sm italic text-ink-muted">{t('results.time.urgency')}</p>
    </div>
  )
}
