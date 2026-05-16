'use client'

import { useState } from 'react'

type Config = {
  starting_capital: string
  income_tax_slab_rate: string
  stcg_rate: string
  ltcg_rate: string
  ltcg_annual_exemption: string
  liquidbees_annual_yield: string
  brokerage_rate: string
  stt_rate_sell: string
  max_position_pct: string
  max_portfolio_heat_pct: string
  drawdown_circuit_breaker_pct: string
  universe: string
  rebalancing_frequency: string
  label: string
}

const DEFAULTS: Config = {
  starting_capital: '10000000',
  income_tax_slab_rate: '0.30',
  stcg_rate: '0.20',
  ltcg_rate: '0.125',
  ltcg_annual_exemption: '125000',
  liquidbees_annual_yield: '0.067',
  brokerage_rate: '0.005',
  stt_rate_sell: '0.001',
  max_position_pct: '0.05',
  max_portfolio_heat_pct: '0.20',
  drawdown_circuit_breaker_pct: '0.25',
  universe: 'nifty500',
  rebalancing_frequency: 'weekly',
  label: '',
}

function Step1Capital({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Starting Capital</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Portfolio Size (₹)</label>
        <input type="number" value={config.starting_capital} onChange={(e) => onChange('starting_capital', e.target.value)}
          className="w-full mt-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm" />
        <p className="font-sans text-xs text-ink-tertiary mt-1">= ₹{Number(config.starting_capital).toLocaleString('en-IN')}</p>
      </div>
    </div>
  )
}

function Step2Tax({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  const slabOptions = [{ label: '10%', value: '0.10' }, { label: '20%', value: '0.20' }, { label: '30%', value: '0.30' }]
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Tax Profile</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Income Tax Slab (for LiquidBees income)</label>
        <div className="flex gap-2 mt-2">
          {slabOptions.map(({ label, value }) => (
            <button key={value} onClick={() => onChange('income_tax_slab_rate', value)}
              className={`font-sans text-xs px-4 py-2 rounded-[2px] border ${config.income_tax_slab_rate === value ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {[
        { key: 'stcg_rate' as keyof Config, label: 'STCG Rate (held < 365 days)', pct: true },
        { key: 'ltcg_rate' as keyof Config, label: 'LTCG Rate (held ≥ 365 days)', pct: true },
        { key: 'ltcg_annual_exemption' as keyof Config, label: 'LTCG Annual Exemption (₹)', pct: false },
      ].map(({ key, label, pct }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input type="number"
              value={pct ? (Number(config[key]) * 100).toFixed(1) : config[key]}
              onChange={(e) => onChange(key, pct ? String(Number(e.target.value) / 100) : e.target.value)}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm" />
            {pct && <span className="font-sans text-sm text-ink-tertiary">%</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function Step3Cash({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Cash Management</h3>
      <div className="border border-paper-rule rounded-[2px] p-3 bg-paper">
        <p className="font-sans text-sm text-ink-primary">Idle cash deployed as: <strong>LiquidBees (LIQUIDBEES)</strong></p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">Nippon India ETF Liquid BeES — NSE listed, MIBOR-linked yield</p>
      </div>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">LiquidBees Annual Yield Assumption</label>
        <div className="flex items-center gap-2 mt-1">
          <input type="number" step="0.1"
            value={(Number(config.liquidbees_annual_yield) * 100).toFixed(1)}
            onChange={(e) => onChange('liquidbees_annual_yield', String(Number(e.target.value) / 100))}
            className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm" />
          <span className="font-sans text-sm text-ink-tertiary">% p.a.</span>
        </div>
      </div>
      <p className="font-sans text-xs text-ink-tertiary">
        LiquidBees income taxed at {(Number(config.income_tax_slab_rate) * 100).toFixed(0)}% (your income tax slab).
      </p>
    </div>
  )
}

function Step4Costs({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Transaction Costs</h3>
      <div className="flex gap-2">
        {[
          { label: 'Zerodha Delivery', brokerage: '0.005', stt: '0.001' },
          { label: 'Flat 0.1%', brokerage: '0.001', stt: '0.001' },
        ].map(({ label, brokerage, stt }) => (
          <button key={label} onClick={() => { onChange('brokerage_rate', brokerage); onChange('stt_rate_sell', stt) }}
            className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.brokerage_rate === brokerage ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}>
            {label}
          </button>
        ))}
      </div>
      {[
        { key: 'brokerage_rate' as keyof Config, label: 'Brokerage Rate (per side)' },
        { key: 'stt_rate_sell' as keyof Config, label: 'STT Rate (sell side)' },
      ].map(({ key, label }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input type="number" step="0.001"
              value={(Number(config[key]) * 100).toFixed(3)}
              onChange={(e) => onChange(key, String(Number(e.target.value) / 100))}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm" />
            <span className="font-sans text-sm text-ink-tertiary">%</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function Step5Universe({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Universe & Rebalancing</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Universe</label>
        <div className="flex gap-2 mt-2">
          {['nifty50', 'nifty100', 'nifty500'].map((u) => (
            <button key={u} onClick={() => onChange('universe', u)}
              className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.universe === u ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}>
              {u.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Rebalancing Frequency</label>
        <div className="flex gap-2 mt-2">
          {['daily', 'weekly', 'monthly'].map((f) => (
            <button key={f} onClick={() => onChange('rebalancing_frequency', f)}
              className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.rebalancing_frequency === f ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Step6RiskLimits({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Hard Risk Limits</h3>
      <p className="font-sans text-xs text-ink-tertiary">These are hard constraints — not genome variables. They apply to every strategy.</p>
      {[
        { key: 'max_position_pct' as keyof Config, label: 'Max Position Size (per stock)' },
        { key: 'max_portfolio_heat_pct' as keyof Config, label: 'Max Portfolio Heat (% in equities)' },
        { key: 'drawdown_circuit_breaker_pct' as keyof Config, label: 'Drawdown Circuit Breaker' },
      ].map(({ key, label }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input type="number" step="1"
              value={(Number(config[key]) * 100).toFixed(0)}
              onChange={(e) => onChange(key, String(Number(e.target.value) / 100))}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm" />
            <span className="font-sans text-sm text-ink-tertiary">%</span>
          </div>
        </div>
      ))}
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Profile Label (optional)</label>
        <input type="text" value={config.label} onChange={(e) => onChange('label', e.target.value)}
          placeholder="e.g. 30% slab HNI profile"
          className="w-full mt-1 border border-paper-rule rounded-[2px] px-3 py-2 font-sans text-sm" />
      </div>
    </div>
  )
}

export function StrategyConfigurator({ onClose }: { onClose?: () => void }) {
  const [step, setStep] = useState(1)
  const [config, setConfig] = useState<Config>(DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const onChange = (key: keyof Config, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/trading/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      setSaved(true)
      onClose?.()
    } finally {
      setSaving(false)
    }
  }

  const STEPS = [
    { n: 1, label: 'Capital' }, { n: 2, label: 'Tax' }, { n: 3, label: 'Cash' },
    { n: 4, label: 'Costs' }, { n: 5, label: 'Universe' }, { n: 6, label: 'Risk' },
  ]

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper max-w-xl">
      <div className="flex border-b border-paper-rule">
        {STEPS.map(({ n, label }) => (
          <button key={n} onClick={() => setStep(n)}
            className={`flex-1 py-2 font-sans text-xs ${step === n ? 'text-teal-600 border-b-2 border-teal-600' : 'text-ink-tertiary hover:text-ink-secondary'}`}>
            {n}. {label}
          </button>
        ))}
      </div>
      <div className="p-6">
        {step === 1 && <Step1Capital config={config} onChange={onChange} />}
        {step === 2 && <Step2Tax config={config} onChange={onChange} />}
        {step === 3 && <Step3Cash config={config} onChange={onChange} />}
        {step === 4 && <Step4Costs config={config} onChange={onChange} />}
        {step === 5 && <Step5Universe config={config} onChange={onChange} />}
        {step === 6 && <Step6RiskLimits config={config} onChange={onChange} />}
      </div>
      <div className="flex justify-between items-center px-6 py-4 border-t border-paper-rule">
        <button onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step === 1}
          className="font-sans text-xs text-ink-tertiary disabled:opacity-30 hover:text-ink-primary">
          Back
        </button>
        <div className="flex gap-3 items-center">
          {saved && <p className="font-sans text-xs text-teal-600">Saved. Re-running tonight.</p>}
          {step < 6 ? (
            <button onClick={() => setStep((s) => s + 1)}
              className="font-sans text-xs bg-teal-600 text-white px-4 py-2 rounded-[2px] hover:bg-teal-700">
              Next
            </button>
          ) : (
            <button onClick={handleSave} disabled={saving}
              className="font-sans text-xs bg-teal-600 text-white px-4 py-2 rounded-[2px] hover:bg-teal-700 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save Configuration'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
