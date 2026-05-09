'use client'
// allow-large: owns all interactive state for policy admin — tab selection, edit modal, history drawer, and tab body rendering

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { DecisionPolicyRow } from '@/lib/queries/policies'
import type { ThresholdRow, RecentRunRow } from '@/lib/queries/thresholds'
import { RecomputePanel } from '../thresholds/RecomputePanel'
import { GatePoliciesTab } from './GatePoliciesTab'
import { MultipliersTab } from './MultipliersTab'
import { StateCutoffsTab } from './StateCutoffsTab'
import { AdvancedTab } from './AdvancedTab'
import { EditGatePolicyModal } from './EditGatePolicyModal'
import { EditMultiplierModal } from './EditMultiplierModal'
import { PolicyHistoryDrawer } from './PolicyHistoryDrawer'
import { GATE_CONFIG, MULTIPLIER_CONFIG } from '@/lib/policy-catalogs'

type Tab = 'gate-policies' | 'multipliers' | 'state-cutoffs' | 'advanced'

const TABS: { id: Tab; label: string }[] = [
  { id: 'gate-policies', label: 'Gate Policies' },
  { id: 'multipliers', label: 'Multipliers' },
  { id: 'state-cutoffs', label: 'State Cutoffs' },
  { id: 'advanced', label: 'Advanced' },
]

type Props = {
  policies: DecisionPolicyRow[]
  thresholds: ThresholdRow[]
  recentRuns: RecentRunRow[]
}

export function PoliciesView({ policies, thresholds, recentRuns }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('gate-policies')
  const [editingPolicyKey, setEditingPolicyKey] = useState<string | null>(null)
  const [selectedHistoryKey, setSelectedHistoryKey] = useState<string | null>(null)
  const router = useRouter()

  function handleSaved() {
    setEditingPolicyKey(null)
    router.refresh()
  }

  function handleThresholdSaved() {
    router.refresh()
  }

  // Determine what kind of modal to open based on the policy key
  const editingPolicy = editingPolicyKey
    ? policies.find((p) => p.policy_key === editingPolicyKey) ?? null
    : null
  const isGateEdit = editingPolicyKey !== null && editingPolicyKey in GATE_CONFIG
  const isMultiplierEdit = editingPolicyKey !== null && editingPolicyKey in MULTIPLIER_CONFIG

  return (
    <>
      {/* Recompute panel always at top */}
      <RecomputePanel recentRuns={recentRuns} />

      {/* Tab strip */}
      <div className="flex gap-0 border-b border-paper-rule mb-6">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`font-sans text-sm px-4 py-2.5 transition-colors ${
              activeTab === id
                ? 'text-ink-primary border-b-2 border-accent -mb-px'
                : 'text-ink-secondary hover:text-ink-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab body */}
      {activeTab === 'gate-policies' && (
        <GatePoliciesTab
          policies={policies.filter((p) => p.policy_kind === 'gate_states')}
          onEdit={setEditingPolicyKey}
          onHistory={setSelectedHistoryKey}
        />
      )}

      {activeTab === 'multipliers' && (
        <MultipliersTab
          policies={policies.filter((p) => p.policy_kind === 'multiplier_map')}
          onEdit={setEditingPolicyKey}
          onHistory={setSelectedHistoryKey}
        />
      )}

      {activeTab === 'state-cutoffs' && (
        <StateCutoffsTab
          thresholds={thresholds}
          onThresholdSaved={handleThresholdSaved}
        />
      )}

      {activeTab === 'advanced' && (
        <AdvancedTab thresholds={thresholds} recentRuns={recentRuns} />
      )}

      {/* Edit modals */}
      {editingPolicy && isGateEdit && (
        <EditGatePolicyModal
          policy={editingPolicy}
          onClose={() => setEditingPolicyKey(null)}
          onSaved={handleSaved}
        />
      )}

      {editingPolicy && isMultiplierEdit && (
        <EditMultiplierModal
          policy={editingPolicy}
          onClose={() => setEditingPolicyKey(null)}
          onSaved={handleSaved}
        />
      )}

      {/* History drawer */}
      {selectedHistoryKey && (
        <PolicyHistoryDrawer
          policyKey={selectedHistoryKey}
          onClose={() => setSelectedHistoryKey(null)}
        />
      )}
    </>
  )
}
