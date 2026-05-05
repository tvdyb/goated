// The four comps — each is a self-contained view rendered at fixed dimensions
// inside a DCArtboard.

const T = window.TOKENS;

// ═══════════════════════════════════════════════════════════════════
// COMP 1 — Desktop dashboard, 1280px wide
// ═══════════════════════════════════════════════════════════════════
function DesktopDashboard() {
  const [expanded, setExpanded] = React.useState(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [feedOpen, setFeedOpen] = React.useState(false);
  const overrideMap = Object.fromEntries(window.ACCOUNT.theoOverrides.map(o => [o.ticker, o]));

  return (
    <div style={{ background: T.bgBase, color: T.inkHi, fontFamily: 'Inter, system-ui', height: '100%' }}>
      <StatusBar account={window.ACCOUNT} />

      <div className="grid" style={{ gridTemplateColumns: drawerOpen ? '1fr 380px' : '1fr', height: 'calc(100% - 48px)' }}>
        {/* Main content */}
        <div className="overflow-auto">
          {/* Zone 2 — Market view */}
          <section className="px-4 pt-3 pb-2">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-baseline gap-2">
                <h2 className="text-[15px] font-semibold tracking-tight" style={{ color: T.inkHi }}>
                  KXISMPMI-26MAY
                </h2>
                <span className="text-[11px]" style={{ color: T.inkLo }}>
                  ISM Manufacturing PMI · {window.STRIKES.length} strikes
                </span>
                <Pill tone="info">5 quoting</Pill>
                <Pill tone="lip">${window.STRIKES.length * 125} LIP/period</Pill>
              </div>
              <div className="flex items-center gap-1">
                <SmallBtn>collapse</SmallBtn>
                <SmallBtn>filter</SmallBtn>
                <SmallBtn>⋯</SmallBtn>
              </div>
            </div>

            <div className="rounded border overflow-hidden" style={{ borderColor: T.border, background: T.surface }}>
              <StrikeGridHeader />
              {window.STRIKES.map(s => (
                <StrikeRow
                  key={s.ticker}
                  s={s}
                  override={overrideMap[s.ticker]}
                  expanded={expanded === s.ticker}
                  onToggle={() => setExpanded(expanded === s.ticker ? null : s.ticker)}
                />
              ))}
            </div>

            {/* "view all programs" */}
            <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: T.inkLo }}>
              <button className="hover:underline">+ Browse all 1,291 active LIP programs</button>
              <span>data is for KXISMPMI-26MAY only — other LIPs hidden</span>
            </div>
          </section>

          {/* Zone 4 — Decision feed (collapsible) */}
          <section className="px-4 pb-3">
            <div className="rounded border" style={{ borderColor: T.border, background: T.surface }}>
              <button onClick={() => setFeedOpen(!feedOpen)}
                      className="w-full flex items-center justify-between px-3 py-2 text-[11px] uppercase tracking-wider"
                      style={{ color: T.inkLo }}>
                <span className="flex items-center gap-2">
                  <span style={{ transform: feedOpen ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: '.15s' }}>▶</span>
                  Decision feed
                  <span style={{ color: T.inkDim, textTransform: 'none', letterSpacing: 0 }}>· last {feedOpen ? window.FEED.length : 3} of 50</span>
                </span>
                <span className="flex items-center gap-1.5" style={{ textTransform: 'none', letterSpacing: 0 }}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: T.yes, boxShadow: `0 0 4px ${T.yes}` }} />
                  <span style={{ color: T.inkLo }}>streaming</span>
                </span>
              </button>
              <div className="px-3 pb-3">
                <DecisionFeed entries={window.FEED} max={feedOpen ? 999 : 3} />
              </div>
            </div>
          </section>
        </div>

        {/* Zone 3 — Operator drawer (collapsed) */}
        {!drawerOpen && (
          <button onClick={() => setDrawerOpen(true)}
                  className="fixed right-4 bottom-16 px-3 py-2 rounded border text-[11px] flex items-center gap-2"
                  style={{ background: T.surface2, color: T.inkHi, borderColor: T.borderStrong, fontFamily: 'Inter, system-ui' }}>
            <span style={{ color: T.info }}>⚙</span>
            Operator
            {(window.ACCOUNT.theoOverrides.length + window.ACCOUNT.sideLocks.length + Object.keys(window.ACCOUNT.knobOverrides).length) > 0 && (
              <Pill tone="info">{window.ACCOUNT.theoOverrides.length + Object.keys(window.ACCOUNT.knobOverrides).length} active</Pill>
            )}
          </button>
        )}
        {drawerOpen && <OperatorDrawer onClose={() => setDrawerOpen(false)} />}
      </div>

      {/* Floating bottom-right operator pill */}
      <div className="fixed bottom-3 left-4 text-[10px] flex items-center gap-3" style={{ color: T.inkDim, fontFamily: 'JetBrains Mono, ui-monospace' }}>
        <span>v{window.ACCOUNT.version}</span>
        <span>cycle 2,847</span>
        <span>5s tick · 142ms last</span>
      </div>
    </div>
  );
}

function SmallBtn({ children, onClick }) {
  return (
    <button onClick={onClick} className="text-[11px] px-2 py-1 rounded border hover:brightness-125"
            style={{ background: T.surface, color: T.inkMid, borderColor: T.border }}>
      {children}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Operator drawer — used in desktop comp (collapsed) AND comp 3 (expanded)
// ═══════════════════════════════════════════════════════════════════
function OperatorDrawer({ onClose, defaultTab = 'theos' }) {
  const [tab, setTab] = React.useState(defaultTab);
  return (
    <aside className="border-l flex flex-col"
           style={{ background: T.bgRaise, borderColor: T.border, height: '100%' }}>
      <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: T.border }}>
        <div className="flex items-center gap-2">
          <span style={{ color: T.info }}>⚙</span>
          <span className="text-[12px] font-semibold tracking-tight" style={{ color: T.inkHi }}>Operator</span>
        </div>
        <button onClick={onClose} className="text-[14px] leading-none px-1" style={{ color: T.inkLo }}>✕</button>
      </div>

      {/* Tabs */}
      <div className="flex border-b" style={{ borderColor: T.border }}>
        {[
          ['theos',   'Theos',   window.ACCOUNT.theoOverrides.length],
          ['pauses',  'Pauses',  0],
          ['knobs',   'Knobs',   Object.keys(window.ACCOUNT.knobOverrides).length],
          ['locks',   'Locks',   window.ACCOUNT.sideLocks.length],
          ['manual',  'Manual',  null],
        ].map(([k, label, count]) => (
          <button key={k} onClick={() => setTab(k)}
                  className="flex-1 px-2 py-2 text-[11px] uppercase tracking-wider relative"
                  style={{ color: tab === k ? T.inkHi : T.inkLo }}>
            <span className="flex items-center justify-center gap-1.5">
              {label}
              {count != null && count > 0 && (
                <span className="text-[9px] px-1 rounded-sm tabular-nums"
                      style={{ background: T.surface2, color: T.info, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  {count}
                </span>
              )}
            </span>
            {tab === k && <span className="absolute -bottom-px inset-x-2 h-px" style={{ background: T.info }} />}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-3">
        {tab === 'theos' && <TheosTab />}
        {tab === 'pauses' && <PausesTab />}
        {tab === 'knobs' && <KnobsTab />}
        {tab === 'locks' && <LocksTab />}
        {tab === 'manual' && <ManualOrderTab />}
      </div>
    </aside>
  );
}

function TheosTab() {
  const overrides = window.ACCOUNT.theoOverrides;
  return (
    <div>
      <div className="text-[10px] mb-3 px-2 py-1.5 rounded border flex items-start gap-2"
           style={{ background: T.surface, borderColor: T.border, color: T.inkLo }}>
        <span style={{ color: T.warn }}>⚠</span>
        Overrides clear on bot restart. Set per-strike inline from the grid.
      </div>
      <div className="text-[9px] uppercase tracking-wider mb-2" style={{ color: T.inkLo }}>
        Active ({overrides.length})
      </div>
      {overrides.length === 0 ? (
        <div className="text-[11px]" style={{ color: T.inkDim }}>no overrides — strategy uses TheoProvider</div>
      ) : (
        <div className="space-y-2">
          {overrides.map((o, i) => (
            <div key={i} className="rounded border p-2" style={{ background: T.surface, borderColor: T.border }}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] tabular-nums" style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  …{o.ticker.slice(-9)}
                </span>
                <span className="text-[13px] font-semibold tabular-nums" style={{ color: T.lip, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  {o.yesC}¢
                </span>
              </div>
              <div className="text-[10px] leading-relaxed" style={{ color: T.inkLo }}>
                "{o.reason}"
              </div>
              <div className="mt-1.5 flex items-center justify-between text-[9px]" style={{ color: T.inkDim, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                <span>by {o.actor} @ {o.setAt} · conf {o.conf.toFixed(2)}</span>
                <button className="hover:underline" style={{ color: T.no }}>clear</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button className="mt-3 w-full text-[11px] font-semibold px-2 py-2 rounded border"
              style={{ background: T.surface, color: T.inkLo, borderColor: T.border, borderStyle: 'dashed' }}>
        Clear all overrides
      </button>
    </div>
  );
}

function PausesTab() {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider mb-2" style={{ color: T.inkLo }}>Global</div>
      <div className="rounded border p-3 mb-3 flex items-center justify-between"
           style={{ background: T.surface, borderColor: T.border }}>
        <div>
          <div className="text-[12px] font-semibold" style={{ color: T.yes }}>Running</div>
          <div className="text-[10px]" style={{ color: T.inkLo }}>strategy quotes every 5s</div>
        </div>
        <button className="text-[11px] px-2.5 py-1.5 rounded border"
                style={{ background: '#2b2210', color: T.warn, borderColor: '#5a4923' }}>
          Pause all
        </button>
      </div>

      <div className="text-[9px] uppercase tracking-wider mb-2" style={{ color: T.inkLo }}>Per ticker / side</div>
      <div className="text-[11px] mb-2" style={{ color: T.inkDim }}>none paused</div>
      <div className="rounded border p-2" style={{ background: T.surface, borderColor: T.border }}>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <Field label="Ticker">
            <input className="w-full bg-transparent outline-none text-[12px]" placeholder="KX…"
                   style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
          </Field>
          <Field label="Side">
            <select className="w-full bg-transparent outline-none text-[12px]"
                    style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
              <option>ticker only</option>
              <option>bid</option>
              <option>ask</option>
            </select>
          </Field>
        </div>
        <button className="w-full text-[11px] font-semibold px-2 py-1.5 rounded border"
                style={{ background: '#2b2210', color: T.warn, borderColor: '#5a4923' }}>
          Pause
        </button>
      </div>
    </div>
  );
}

function KnobsTab() {
  const knobs = [
    { name: 'min_theo_confidence', cur: 0.65, def: 0.50, lo: 0, hi: 1, step: 0.05 },
    { name: 'theo_tolerance_c',    cur: null, def: 2.0,  lo: 0, hi: 50, step: 0.5 },
    { name: 'max_distance_from_best', cur: null, def: 5.0, lo: 0, hi: 50, step: 0.5 },
    { name: 'dollars_per_side',    cur: null, def: 5.0,  lo: 0, hi: 100, step: 1 },
  ];
  return (
    <div className="space-y-3">
      {knobs.map(k => (
        <div key={k.name} className="rounded border p-2.5" style={{ background: T.surface, borderColor: T.border }}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] tabular-nums" style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
              {k.name}
            </span>
            {k.cur != null
              ? <Pill tone="info">override</Pill>
              : <span className="text-[9px] uppercase tracking-wider" style={{ color: T.inkDim }}>default</span>}
          </div>
          <div className="flex items-center gap-2">
            <input type="range" min={k.lo} max={k.hi} step={k.step} defaultValue={k.cur ?? k.def}
                   className="flex-1" style={{ accentColor: T.info }} />
            <span className="text-[12px] tabular-nums w-12 text-right" style={{ color: k.cur != null ? T.info : T.inkLo, fontFamily: 'JetBrains Mono, ui-monospace' }}>
              {(k.cur ?? k.def).toFixed(2)}
            </span>
          </div>
          <div className="flex items-center justify-between text-[9px] mt-1" style={{ color: T.inkDim, fontFamily: 'JetBrains Mono, ui-monospace' }}>
            <span>{k.lo}</span>
            <span>default {k.def.toFixed(2)}</span>
            <span>{k.hi}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function LocksTab() {
  return (
    <div>
      <div className="text-[10px] mb-3 px-2 py-1.5 rounded border" style={{ background: T.surface, borderColor: T.border, color: T.inkLo }}>
        Locks force strategy <code style={{ color: T.inkHi }}>skip=True</code> on a side until cleared. Stronger than pauses.
      </div>
      <div className="text-[11px] mb-2" style={{ color: T.inkDim }}>no locks active</div>
      <div className="rounded border p-2 space-y-2" style={{ background: T.surface, borderColor: T.border }}>
        <Field label="Ticker">
          <input className="w-full bg-transparent outline-none text-[12px]" placeholder="KX…"
                 style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Side">
            <select className="w-full bg-transparent outline-none text-[12px]" style={{ color: T.inkHi }}>
              <option>bid</option>
              <option>ask</option>
            </select>
          </Field>
          <Field label="TTL (s, optional)">
            <input className="w-full bg-transparent outline-none text-[12px]" placeholder="3600"
                   style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
          </Field>
        </div>
        <Field label="Reason">
          <input className="w-full bg-transparent outline-none text-[12px]" placeholder="why?"
                 style={{ color: T.inkHi }} />
        </Field>
        <button className="w-full text-[11px] font-semibold px-2 py-1.5 rounded border"
                style={{ background: T.dangerDim, color: T.danger, borderColor: '#7a2a32' }}>
          Lock side
        </button>
      </div>
    </div>
  );
}

function ManualOrderTab() {
  return (
    <div>
      <div className="text-[10px] mb-3 px-2 py-1.5 rounded border flex gap-2" style={{ background: T.surface, borderColor: T.border, color: T.inkLo }}>
        <span style={{ color: T.warn }}>⚠</span>
        Manual orders are blocked when kill is engaged.
      </div>
      <div className="rounded border p-2 space-y-2" style={{ background: T.surface, borderColor: T.border }}>
        <Field label="Ticker">
          <input className="w-full bg-transparent outline-none text-[12px]" placeholder="KX… (or click a Yes/No badge)"
                 style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Side">
            <select className="w-full bg-transparent outline-none text-[12px]" style={{ color: T.inkHi }}>
              <option>bid (buy Yes)</option>
              <option>ask (sell Yes)</option>
            </select>
          </Field>
          <Field label="Count">
            <input className="w-full bg-transparent outline-none text-[12px]" placeholder="10"
                   style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Limit (cents)">
            <input className="w-full bg-transparent outline-none text-[12px]" placeholder="49"
                   style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
          </Field>
          <Field label="Lock side after?">
            <select className="w-full bg-transparent outline-none text-[12px]" style={{ color: T.inkHi }}>
              <option>no</option>
              <option>yes</option>
            </select>
          </Field>
        </div>
        <Field label="Reason">
          <input className="w-full bg-transparent outline-none text-[12px]" placeholder="audit string"
                 style={{ color: T.inkHi }} />
        </Field>
        <div className="flex items-center justify-between text-[10px]" style={{ color: T.inkLo, fontFamily: 'JetBrains Mono, ui-monospace' }}>
          <span>notional: <span style={{ color: T.inkHi }}>$4.90</span></span>
          <span>cash after: <span style={{ color: T.inkHi }}>$94.27</span></span>
        </div>
        <button className="w-full text-[11px] font-semibold px-2 py-1.5 rounded border"
                style={{ background: '#0a1f17', color: T.yes, borderColor: '#164d3a' }}>
          Submit (Cmd+Enter)
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// COMP 2 — Mobile, 390px wide
// ═══════════════════════════════════════════════════════════════════
function MobileDashboard() {
  const [expanded, setExpanded] = React.useState(null);
  const overrideMap = Object.fromEntries(window.ACCOUNT.theoOverrides.map(o => [o.ticker, o]));

  return (
    <div style={{ background: T.bgBase, color: T.inkHi, fontFamily: 'Inter, system-ui', height: '100%', position: 'relative' }}>
      <StatusBar account={window.ACCOUNT} compact />

      <div className="overflow-auto" style={{ height: 'calc(100% - 100px)' }}>
        {/* Mini ribbon for second row */}
        <div className="px-3 py-2 flex items-center gap-2 text-[10px] border-b"
             style={{ borderColor: T.border, background: T.bgRaise, fontFamily: 'JetBrains Mono, ui-monospace', color: T.inkLo }}>
          <span>cash <span style={{ color: T.inkHi }}>${window.ACCOUNT.cash.toFixed(2)}</span></span>
          <span>port <span style={{ color: T.inkHi }}>${window.ACCOUNT.port.toFixed(2)}</span></span>
          <span style={{ marginLeft: 'auto', color: T.inkDim }}>v{window.ACCOUNT.version}</span>
        </div>

        {/* Event header */}
        <div className="px-3 pt-3 pb-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[14px] font-semibold tracking-tight">KXISMPMI-26MAY</h2>
            <span className="text-[10px]" style={{ color: T.inkLo }}>8 strikes</span>
          </div>
          <div className="text-[10px] mt-0.5" style={{ color: T.inkLo }}>ISM Manufacturing PMI ≥ N this month</div>
          <div className="flex items-center gap-1.5 mt-2">
            <Pill tone="info">5 quoting</Pill>
            <Pill tone="lip">$1,000 LIP</Pill>
            <Pill tone="lip">2 theos</Pill>
          </div>
        </div>

        {/* Strike list */}
        <div className="border-y" style={{ borderColor: T.border, background: T.surface }}>
          {window.STRIKES.map(s => (
            <StrikeRow
              key={s.ticker}
              s={s}
              density="mobile"
              override={overrideMap[s.ticker]}
              expanded={expanded === s.ticker}
              onToggle={() => setExpanded(expanded === s.ticker ? null : s.ticker)}
            />
          ))}
        </div>

        {/* Decision feed */}
        <div className="px-3 pt-3 pb-20">
          <div className="text-[9px] uppercase tracking-wider mb-2 flex items-center gap-2" style={{ color: T.inkLo }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: T.yes }} />
            Decisions · live
          </div>
          <div className="rounded border" style={{ borderColor: T.border, background: T.surface }}>
            <div className="px-2 py-1">
              <DecisionFeed entries={window.FEED} max={3} compact />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom-sheet button row */}
      <div className="absolute bottom-0 inset-x-0 px-3 py-2.5 flex items-center gap-2 border-t"
           style={{ background: T.bgRaise, borderColor: T.border }}>
        <button className="flex-1 text-[12px] font-semibold py-2 rounded border flex items-center justify-center gap-1.5"
                style={{ background: T.surface, color: T.inkHi, borderColor: T.border }}>
          <span style={{ color: T.info }}>⚙</span> Operator
          <Pill tone="info">3</Pill>
        </button>
        <button className="text-[12px] font-semibold py-2 px-3 rounded border"
                style={{ background: T.surface, color: T.inkMid, borderColor: T.border }}>
          ☰ Feed
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// COMP 3 — Operator drawer expanded (full-bleed view of the drawer)
// ═══════════════════════════════════════════════════════════════════
function OperatorDrawerComp() {
  const [tab, setTab] = React.useState('theos');
  return (
    <div style={{ background: T.bgBase, color: T.inkHi, fontFamily: 'Inter, system-ui', height: '100%' }}>
      <StatusBar account={window.ACCOUNT} />
      <div className="flex" style={{ height: 'calc(100% - 48px)' }}>
        {/* preview of grid behind */}
        <div className="flex-1 px-4 py-3 opacity-40">
          <div className="text-[11px] mb-2" style={{ color: T.inkLo }}>KXISMPMI-26MAY · 8 strikes</div>
          <div className="rounded border" style={{ borderColor: T.border, background: T.surface }}>
            <StrikeGridHeader />
            {window.STRIKES.slice(0, 5).map(s => (
              <div key={s.ticker} className="grid items-center gap-3 px-3 py-2 border-b"
                   style={{ borderColor: T.border, gridTemplateColumns: '1fr 70px 52px 52px 90px 130px 78px 90px 16px' }}>
                <div className="text-[12px]" style={{ color: T.inkHi }}>{s.label}</div>
                <div className="text-right text-[12px] tabular-nums" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>{s.yesC}%</div>
                <PriceChip side="yes" c={s.yesC} dim />
                <PriceChip side="no" c={s.noC} dim />
                <div></div><div></div><div></div><div></div><div></div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ width: 460 }}>
          <OperatorDrawer onClose={() => {}} defaultTab={tab} />
        </div>
      </div>

      {/* Tab callouts */}
      <div className="absolute pointer-events-none" style={{ top: 80, left: 16 }}>
        <div className="text-[9px] uppercase tracking-[0.18em] px-2 py-1 rounded border inline-block"
             style={{ background: T.surface2, color: T.inkLo, borderColor: T.border }}>
          Operator → 5 tabs
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// COMP 4 — Expanded strike row
// ═══════════════════════════════════════════════════════════════════
function ExpandedRowComp() {
  const s = window.STRIKES[2]; // strike 51, has position + resting + theo override
  const override = window.ACCOUNT.theoOverrides.find(o => o.ticker === s.ticker);
  return (
    <div style={{ background: T.bgBase, color: T.inkHi, fontFamily: 'Inter, system-ui', height: '100%', padding: 16 }}>
      <div className="text-[11px] mb-2 flex items-baseline gap-2" style={{ color: T.inkLo }}>
        <span style={{ color: T.inkHi, fontWeight: 600 }}>KXISMPMI-26MAY</span>
        · expanded view of strike "At least 51"
      </div>
      <div className="rounded border overflow-hidden" style={{ borderColor: T.border, background: T.surface }}>
        <StrikeGridHeader />
        {/* the row above */}
        <div className="opacity-40">
          <StrikeRow s={window.STRIKES[1]} />
        </div>
        {/* the expanded row */}
        <StrikeRow s={s} expanded override={override} />
        {/* row below */}
        <div className="opacity-40">
          <StrikeRow s={window.STRIKES[3]} />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3 text-[10px]" style={{ color: T.inkLo, fontFamily: 'Inter, system-ui' }}>
        <Callout label="Order book — top 5">
          ⚠ requires new <code style={{ color: T.inkHi }}>orderbook</code> WS broadcast (we have it internally each cycle, not yet emitted).
        </Callout>
        <Callout label="Resting orders">
          From <code style={{ color: T.inkHi }}>runtime.resting_orders</code>. Cancel hits existing <code style={{ color: T.inkHi }}>POST /control/cancel</code>.
        </Callout>
        <Callout label="LIP detail">
          From <code style={{ color: T.inkHi }}>incentives.programs[]</code>. Filled count is new — needs additive fill counter on the program record.
        </Callout>
      </div>
    </div>
  );
}

function Callout({ label, children }) {
  return (
    <div className="rounded border p-2.5" style={{ background: T.surface, borderColor: T.border }}>
      <div className="text-[9px] uppercase tracking-wider mb-1" style={{ color: T.inkLo }}>{label}</div>
      <div style={{ color: T.inkLo, lineHeight: 1.5 }}>{children}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// COMP 5 — Tokens & type scale
// ═══════════════════════════════════════════════════════════════════
function TokensComp() {
  const swatches = [
    ['Surfaces', [
      ['bg-base', T.bgBase], ['bg-raise', T.bgRaise],
      ['surface', T.surface], ['surface-2', T.surface2], ['surface-3', T.surface3],
      ['border', T.border], ['border-strong', T.borderStrong],
    ]],
    ['Ink', [
      ['ink-hi', T.inkHi], ['ink-mid', T.inkMid], ['ink-lo', T.inkLo], ['ink-dim', T.inkDim],
    ]],
    ['Semantic', [
      ['yes / long',  T.yes], ['no / short', T.no],
      ['info',        T.info], ['warn',       T.warn],
      ['lip-gold',    T.lip], ['danger',     T.danger],
    ]],
  ];
  const types = [
    ['display',  18, 600, 'Inter', 'KXISMPMI-26MAY · 8 strikes'],
    ['title',    15, 600, 'Inter', 'At least 51'],
    ['body',     13, 500, 'Inter', 'Operator drawer'],
    ['data',     13, 600, 'JetBrains Mono', '49¢  +2 Y  $0.43'],
    ['label',    11, 500, 'Inter', 'last 3 of 50'],
    ['caption',  10, 400, 'Inter', '14:02:34 · KXISMPMI-26MAY-51'],
    ['micro',    9,  500, 'Inter', 'STRIKE  % CHANCE  YES  NO'],
  ];
  return (
    <div style={{ background: T.bgBase, color: T.inkHi, padding: 24, height: '100%', overflow: 'auto', fontFamily: 'Inter, system-ui' }}>
      <h2 className="text-[18px] font-semibold mb-1">Design tokens</h2>
      <p className="text-[12px] mb-6" style={{ color: T.inkLo }}>Map straight onto Tailwind theme extension. All hex.</p>

      <div className="grid grid-cols-3 gap-6 mb-8">
        {swatches.map(([cat, items]) => (
          <div key={cat}>
            <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: T.inkLo }}>{cat}</div>
            <div className="space-y-1.5">
              {items.map(([name, hex]) => (
                <div key={name} className="flex items-center gap-2 rounded border p-1.5"
                     style={{ background: T.surface, borderColor: T.border }}>
                  <div className="w-8 h-8 rounded-sm border" style={{ background: hex, borderColor: T.borderStrong }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-semibold" style={{ color: T.inkHi }}>{name}</div>
                    <div className="text-[10px] tabular-nums" style={{ color: T.inkLo, fontFamily: 'JetBrains Mono, ui-monospace' }}>{hex}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <h2 className="text-[14px] font-semibold mb-3">Type scale</h2>
      <div className="rounded border divide-y" style={{ background: T.surface, borderColor: T.border }}>
        {types.map(([name, size, weight, family, sample]) => (
          <div key={name} className="grid items-center gap-3 px-3 py-2"
               style={{ gridTemplateColumns: '90px 60px 100px 1fr', borderColor: T.border }}>
            <div className="text-[11px]" style={{ color: T.inkLo }}>{name}</div>
            <div className="text-[11px] tabular-nums" style={{ color: T.inkMid, fontFamily: 'JetBrains Mono, ui-monospace' }}>{size}px / {weight}</div>
            <div className="text-[11px]" style={{ color: T.inkMid }}>{family}</div>
            <div style={{ fontSize: size, fontWeight: weight, fontFamily: family + ', system-ui' }}>{sample}</div>
          </div>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-[14px] font-semibold mb-3">Row state cues</h2>
          <div className="rounded border overflow-hidden" style={{ borderColor: T.border, background: T.surface }}>
            <CueRow color="transparent" label="default — no skin" />
            <CueRow color={T.info}       label="we have resting orders" />
            <CueRow color={T.lip}        label="manual theo override active" />
            <CueRow color={T.no}         label="recent fill (last 60s)" tint="rgba(255,122,138,0.04)" />
            <CueRow color={T.yes}        tint="rgba(61,220,151,0.04)" label="we have a position" />
          </div>
        </div>

        <div>
          <h2 className="text-[14px] font-semibold mb-3">Pill family</h2>
          <div className="flex flex-wrap gap-2 rounded border p-3" style={{ borderColor: T.border, background: T.surface }}>
            <Pill tone="live" dot>live</Pill>
            <Pill tone="info">5 quoting</Pill>
            <Pill tone="lip">$125</Pill>
            <Pill tone="warn">paused</Pill>
            <Pill tone="danger" dot>error</Pill>
            <Pill tone="pos">+2 Y</Pill>
            <Pill tone="neg">-3 N</Pill>
            <Pill tone="neutral">v142</Pill>
          </div>
          <div className="mt-4 flex items-center gap-3 rounded border p-3" style={{ borderColor: T.border, background: T.surface }}>
            <PriceChip side="yes" c={49} />
            <PriceChip side="no" c={52} />
            <PriceChip side="yes" c={49} big />
            <span className="text-[10px]" style={{ color: T.inkLo }}>price chips — clickable to seed manual order</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function CueRow({ color, label, tint }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 border-b"
         style={{ borderLeft: `2px solid ${color}`, borderColor: T.border, background: tint || 'transparent' }}>
      <span className="text-[11px]" style={{ color: T.inkHi }}>example row</span>
      <span className="text-[10px] ml-auto" style={{ color: T.inkLo }}>{label}</span>
    </div>
  );
}

Object.assign(window, {
  DesktopDashboard, MobileDashboard, OperatorDrawerComp, ExpandedRowComp, TokensComp,
});
