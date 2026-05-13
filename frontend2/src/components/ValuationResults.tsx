import type { ValuationResponse, ValuationRequest, LeadInfo } from '@/lib/types'
import { HeroBlock } from './results/HeroBlock'
import { MarketRealityBlock } from './results/MarketRealityBlock'
import { HowWeGotThereBlock } from './results/HowWeGotThereBlock'
import { PositioningBlock } from './results/PositioningBlock'
import { ZoneMapBlock } from './results/ZoneMapBlock'
import { TimeOnMarketBlock } from './results/TimeOnMarketBlock'
import { ComparablesBlock } from './results/ComparablesBlock'
import { ConversionSignalsBlock } from './results/ConversionSignalsBlock'

interface ValuationResultsProps {
  result: ValuationResponse
  request: ValuationRequest
  lead?: LeadInfo
  onReset: () => void
}

export function ValuationResults({ result, request, lead, onReset }: ValuationResultsProps) {
  const { stats, listings, municipio, search_metadata, search_url, market_transactions } = result

  const showMarketReality =
    market_transactions?.summary?.asking_vs_closing_gap_pct != null &&
    stats.estimated_value != null

  const showPositioning =
    stats.avg_price_per_m2 != null &&
    listings.filter((l) => l.price_per_m2 != null).length >= 3

  const showTimeOnMarket =
    market_transactions != null &&
    market_transactions.transactions.filter((tx) => tx.days_on_market != null).length >= 3

  return (
    <div className="flex flex-col gap-xl">
      {/* 1. Hero */}
      <HeroBlock
        stats={stats}
        municipio={municipio}
        searchMetadata={search_metadata}
        m2={request.m2}
        onReset={onReset}
      />

      {/* 2. Market Reality */}
      {showMarketReality && (
        <MarketRealityBlock
          marketTransactions={market_transactions!}
          estimatedValue={stats.estimated_value!}
          municipioName={municipio.name}
        />
      )}

      {/* 3. How We Got There */}
      {search_metadata.stages.length > 0 && (
        <HowWeGotThereBlock
          searchMetadata={search_metadata}
          searchUrl={search_url}
          stats={stats}
          listings={listings}
        />
      )}

      {/* 4. Positioning */}
      {showPositioning && (
        <PositioningBlock
          listings={listings}
          bedrooms={request.bedrooms}
          m2={request.m2}
          avgPricePerM2={stats.avg_price_per_m2!}
        />
      )}

      {/* 5. Zone Map */}
      <ZoneMapBlock
        municipio={municipio}
        selectedAddress={request.selected_address}
        transactions={market_transactions?.transactions ?? []}
        finalStage={search_metadata.final_stage}
      />

      {/* 6. Time on Market */}
      {showTimeOnMarket && (
        <TimeOnMarketBlock transactions={market_transactions!.transactions} />
      )}

      {/* 7. Comparables */}
      {listings.length > 0 && (
        <ComparablesBlock listings={listings} requestM2={request.m2} />
      )}

      {/* 8. Conversion Signals */}
      <ConversionSignalsBlock
        lead={lead}
        totalTransactions={market_transactions?.summary?.total_transactions}
      />
    </div>
  )
}
