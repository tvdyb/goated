// Shared primitives used across all four comps.
// Pure presentational components — no app-level state.

const T = window.TOKENS;

// ── tiny helpers ────────────────────────────────────────────────────
const cls = (...xs) => xs.filter(Boolean).join(' ');
const fmtC  = (c) => `${c}¢`;
const fmtUsd = (n, signed = false) => {
  const v = (signed && n >= 0 ? '+' : '') + (n < 0 ? '-' : '') + '$' + Math.abs(n).toFixed(2);
  return v.replace('+-', '-');
};
const fmtTimeLeft = (s) => {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};

// ── pills ───────────────────────────────────────────────────────────
function Pill({ tone = 'neutral', children, dot, className }) {
  const tones = {
    live:    { bg: '#0f2a1f', fg: T.yes,  bd: '#1f6e54' },
    danger:  { bg: '#2a0d12', fg: T.no,   bd: '#7a3340' },
    info:    { bg: '#0e2238', fg: T.info, bd: '#28486e' },
    warn:    { bg: '#2b2210', fg: T.warn, bd: '#5a4923' },
    lip:     { bg: '#2b2410', fg: T.lip,  bd: '#5a4923' },
    pos:     { bg: '#0f2a1f', fg: T.yes,  bd: '#1f6e54' },
    neg:     { bg: '#2a0d12', fg: T.no,   bd: '#7a3340' },
    neutral: { bg: T.surface2, fg: T.inkMid, bd: T.border },
    ghost:   { bg: 'transparent', fg: T.inkMid, bd: T.border },
  }[tone];
  return (
    <span
      className={cls('inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded-sm border', className)}
      style={{ background: tones.bg, color: tones.fg, borderColor: tones.bd, fontFamily: 'Inter, system-ui' }}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full" style={{ background: tones.fg, boxShadow: tone === 'live' ? `0 0 6px ${tones.fg}` : 'none' }} />}
      {children}
    </span>
  );
}

// price chip (Yes / No badges) — span+role to avoid nested-button DOM error
function PriceChip({ side, c, big = false, dim = false, onClick }) {
  const isYes = side === 'yes';
  const fg = isYes ? T.yes : T.no;
  const bg = isYes ? '#0a1f17' : '#1f0a0e';
  const bd = isYes ? '#164d3a' : '#4d1a23';
  return (
    <span
      role="button"
      tabIndex={0}
      onClick={(e) => { e.stopPropagation(); onClick?.(e); }}
      className={cls(
        'inline-flex flex-col items-center justify-center rounded leading-none border transition-colors hover:brightness-125 cursor-pointer select-none',
        big ? 'px-3 py-1.5' : 'px-2 py-1',
      )}
      style={{
        background: dim ? T.surface2 : bg,
        color: dim ? T.inkLo : fg,
        borderColor: dim ? T.border : bd,
        fontFamily: 'JetBrains Mono, ui-monospace',
        width: big ? 64 : 52,
      }}
    >
      <span className="text-[9px] uppercase tracking-wider opacity-70">{isYes ? 'Yes' : 'No'}</span>
      <span className={big ? 'text-base font-semibold' : 'text-[13px] font-semibold'}>{c}¢</span>
    </span>
  );
}

// ── status bar (Zone 1) ─────────────────────────────────────────────
function StatusBar({ compact = false, account, onKill }) {
  return (
    <div
      className="flex items-center justify-between px-4 border-b"
      style={{ background: T.bgRaise, borderColor: T.border, height: compact ? 44 : 48 }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2">
          <div className="w-1 h-5 rounded-sm" style={{ background: T.yes, boxShadow: `0 0 8px ${T.yes}` }} />
          <span className="text-[13px] font-semibold tracking-tight" style={{ color: T.inkHi }}>lipmm</span>
        </div>
        <Pill tone="live" dot>live</Pill>
        {!compact && <Pill tone="neutral">{account.tabs} tab</Pill>}
        <div className="h-5 w-px" style={{ background: T.border }} />
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wider" style={{ color: T.inkLo }}>PnL</span>
          <span className="text-[13px] font-semibold tabular-nums" style={{ color: account.pnl >= 0 ? T.yes : T.no, fontFamily: 'JetBrains Mono, ui-monospace' }}>
            {account.pnl >= 0 ? '+' : ''}${account.pnl.toFixed(2)}
          </span>
        </div>
        {!compact && (
          <>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider" style={{ color: T.inkLo }}>cash</span>
              <span className="text-[13px] tabular-nums" style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                ${account.cash.toFixed(2)}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider" style={{ color: T.inkLo }}>port</span>
              <span className="text-[13px] tabular-nums" style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                ${account.port.toFixed(2)}
              </span>
            </div>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onKill}
          className="px-3 py-1 text-[12px] font-semibold rounded border transition-colors"
          style={{
            background: account.killState === 'off' ? T.dangerDim : (account.killState === 'killed' ? '#5a1820' : '#3a2810'),
            color: account.killState === 'off' ? T.danger : (account.killState === 'killed' ? T.danger : T.warn),
            borderColor: account.killState === 'off' ? '#7a2a32' : '#7a4220',
            fontFamily: 'Inter, system-ui',
          }}
        >
          {account.killState === 'off' ? 'KILL' : account.killState === 'killed' ? 'ARM' : 'RESUME'}
        </button>
        {!compact && (
          <button className="text-[12px] hover:underline" style={{ color: T.inkLo }}>Sign out</button>
        )}
      </div>
    </div>
  );
}

// ── strike row (Zone 2 main element) ────────────────────────────────
// columns:  THRESH  CHANCE  YES  NO  POS  RESTING  LIP  THEO
// shared between desktop/mobile/expanded comps with different density modes
function StrikeRow({
  s, density = 'desktop', expanded = false, onToggle, onTheo, onCancel,
  override, // theo override object if present
}) {
  const hasPos = s.pos !== 0;
  const hasResting = s.resting && s.resting.length > 0;
  const hasOverride = !!override;
  const recentFill = s.resting && s.resting.some(r => r.recentFill);
  const isMobile = density === 'mobile';

  // Row tint
  const tint = hasPos
    ? (s.pos > 0 ? 'rgba(61, 220, 151, 0.04)' : 'rgba(255, 122, 138, 0.04)')
    : 'transparent';
  const leftBorder = recentFill
    ? T.no
    : hasOverride
    ? T.lip
    : hasResting
    ? T.info
    : 'transparent';

  return (
    <div
      className="border-b"
      style={{ borderColor: T.border, background: tint, borderLeft: `2px solid ${leftBorder}` }}
    >
      {/* Main row */}
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        className="w-full text-left grid items-center gap-3 px-3 py-2 hover:bg-white/[0.02] transition-colors cursor-pointer"
        style={{
          gridTemplateColumns: isMobile
            ? '1fr 52px 52px 16px'
            : '1fr 70px 52px 52px 90px 130px 78px 90px 16px',
        }}
      >
        {/* Threshold name + ticker */}
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-semibold whitespace-nowrap" style={{ color: T.inkHi, fontFamily: 'Inter, system-ui' }}>
              {s.label}
            </span>
            {hasOverride && <Pill tone="lip" className="!text-[8px] !px-1 !py-0">manual</Pill>}
          </div>
          <div className="text-[10px] tabular-nums whitespace-nowrap" style={{ color: T.inkDim, fontFamily: 'JetBrains Mono, ui-monospace' }}>
            …{s.ticker.slice(-6)}
          </div>
        </div>

        {/* % chance */}
        {!isMobile && (
          <div className="text-right">
            <div className="text-[15px] font-semibold tabular-nums" style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }}>
              {s.yesC}%
            </div>
            <ChanceBar c={s.yesC} />
          </div>
        )}

        {/* Yes / No prices */}
        <PriceChip side="yes" c={s.yesC} />
        <PriceChip side="no"  c={s.noC} />

        {/* Position */}
        {!isMobile && (
          <div className="text-right">
            {s.pos === 0 ? (
              <span className="text-[12px]" style={{ color: T.inkDim, fontFamily: 'JetBrains Mono, ui-monospace' }}>—</span>
            ) : (
              <div>
                <div className="text-[13px] font-semibold tabular-nums" style={{ color: s.pos > 0 ? T.yes : T.no, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  {s.pos > 0 ? '+' : ''}{s.pos} {s.pos > 0 ? 'Y' : 'N'}
                </div>
                <div className="text-[10px] tabular-nums" style={{ color: T.inkLo, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  @{s.avgC}¢
                </div>
              </div>
            )}
          </div>
        )}

        {/* Resting */}
        {!isMobile && (
          <div className="text-right">
            {hasResting ? (
              <div className="text-[11px] tabular-nums" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
                {s.resting.map((r, i) => (
                  <div key={i} style={{ color: r.side === 'bid' ? T.yes : T.no }}>
                    {r.side === 'bid' ? 'B' : 'A'} {r.priceC}¢ × {r.size}
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-[12px]" style={{ color: T.inkDim }}>—</span>
            )}
          </div>
        )}

        {/* LIP badge */}
        {!isMobile && (
          <div className="text-right">
            <div className="inline-flex items-center gap-1 text-[11px] font-semibold tabular-nums px-1.5 py-0.5 rounded-sm border"
                 style={{ background: '#1f1a08', color: T.lip, borderColor: '#5a4923', fontFamily: 'JetBrains Mono, ui-monospace' }}>
              ${s.lip.reward}
            </div>
            <LipProgress filled={s.lip.filled} target={s.lip.target} />
          </div>
        )}

        {/* Theo */}
        {!isMobile && (
          <div className="text-right">
            {hasOverride ? (
              <div>
                <div className="text-[12px] font-semibold tabular-nums" style={{ color: T.lip, fontFamily: 'JetBrains Mono, ui-monospace' }}>
                  {override.yesC}¢
                </div>
                <div className="text-[9px]" style={{ color: T.inkDim }}>{override.setAt}</div>
              </div>
            ) : (
              <span className="text-[11px]" style={{ color: T.inkLo }}>
                auto {Math.round(s.theo * 100)}¢
              </span>
            )}
          </div>
        )}

        {/* Caret */}
        <div className={cls('text-[10px] transition-transform', expanded && 'rotate-90')} style={{ color: T.inkDim }}>▶</div>
      </div>

      {/* Mobile secondary row */}
      {isMobile && (
        <div className="px-3 pb-2 flex items-center justify-between gap-2 text-[11px]"
             style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
          {hasPos ? (
            <span style={{ color: s.pos > 0 ? T.yes : T.no }}>
              pos {s.pos > 0 ? '+' : ''}{s.pos}{s.pos > 0 ? 'Y' : 'N'} @{s.avgC}¢
            </span>
          ) : <span style={{ color: T.inkDim }}>flat</span>}
          {hasResting && (
            <span style={{ color: T.info }}>{s.resting.length} resting</span>
          )}
          <span style={{ color: T.lip }}>LIP ${s.lip.reward}</span>
          {hasOverride
            ? <span style={{ color: T.lip }}>theo {override.yesC}¢ ↑</span>
            : <span style={{ color: T.inkLo }}>theo {Math.round(s.theo * 100)}¢</span>}
        </div>
      )}

      {/* Expanded panel */}
      {expanded && (
        <ExpandedStrike s={s} override={override} onTheo={onTheo} onCancel={onCancel} />
      )}
    </div>
  );
}

function ChanceBar({ c }) {
  return (
    <div className="mt-1 ml-auto h-[3px] w-full max-w-[60px] rounded-full overflow-hidden"
         style={{ background: T.surface2 }}>
      <div className="h-full rounded-full" style={{ width: `${c}%`, background: T.info }} />
    </div>
  );
}

function LipProgress({ filled, target }) {
  const pct = Math.min(100, (filled / target) * 100);
  return (
    <div className="mt-1 ml-auto h-[2px] w-full max-w-[50px] rounded-full overflow-hidden"
         style={{ background: T.surface2 }}>
      <div className="h-full" style={{ width: `${pct}%`, background: T.lip }} />
    </div>
  );
}

// ── expanded strike row contents ───────────────────────────────────
function ExpandedStrike({ s, override, onTheo, onCancel }) {
  return (
    <div className="grid gap-4 px-3 py-3 border-t"
         style={{ background: T.bgBase, borderColor: T.border, gridTemplateColumns: '1.4fr 1fr 1.2fr' }}>
      {/* L2 depth */}
      <Section title="Order book — top 5">
        <DepthLadder ticker={s.ticker} center={s.yesC} />
      </Section>

      {/* Resting orders + cancel */}
      <Section title={`Our resting (${s.resting.length})`}>
        {s.resting.length === 0
          ? <div className="text-[11px]" style={{ color: T.inkDim }}>no working orders</div>
          : (
            <div className="space-y-1.5">
              {s.resting.map((r, i) => (
                <div key={i} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded border"
                     style={{ background: T.surface, borderColor: T.border }}>
                  <div className="flex items-center gap-2 text-[11px] tabular-nums" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
                    <span className="px-1.5 py-0.5 rounded-sm border text-[9px] uppercase tracking-wider"
                          style={{ background: r.side === 'bid' ? '#0a1f17' : '#1f0a0e',
                                   color: r.side === 'bid' ? T.yes : T.no,
                                   borderColor: r.side === 'bid' ? '#164d3a' : '#4d1a23' }}>
                      {r.side}
                    </span>
                    <span style={{ color: T.inkHi }}>{r.priceC}¢ × {r.size}</span>
                    <span style={{ color: T.inkDim }}>· {Math.round(r.ageS / 60)}m ago</span>
                  </div>
                  <button onClick={() => onCancel?.(r.id)}
                          className="text-[10px] px-2 py-1 rounded border hover:brightness-125"
                          style={{ background: T.surface2, color: T.no, borderColor: T.noDim, fontFamily: 'Inter, system-ui' }}>
                    cancel
                  </button>
                </div>
              ))}
            </div>
          )}
      </Section>

      {/* LIP detail */}
      <Section title="LIP incentive">
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
          <Datum label="reward" v={`$${s.lip.reward.toFixed(2)}`} accent={T.lip} />
          <Datum label="target" v={`${s.lip.target} ct`} />
          <Datum label="filled" v={`${s.lip.filled} ct`} />
          <Datum label="discount" v={`${(s.lip.discountBps / 100).toFixed(2)}%`} />
          <Datum label="time left" v="5d 4h" />
          <Datum label="ends" v="May 10 18:46" />
        </div>
        <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ background: T.surface2 }}>
          <div className="h-full" style={{ width: `${(s.lip.filled / s.lip.target) * 100}%`, background: T.lip }} />
        </div>
      </Section>

      {/* Theo override form spans full width */}
      <div className="col-span-3 pt-3 border-t" style={{ borderColor: T.border }}>
        <Section title={override ? `Theo override — set ${override.setAt} by ${override.actor}` : 'Set theo override'}>
          <TheoForm s={s} override={override} onSubmit={onTheo} />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.12em] mb-2" style={{ color: T.inkLo, fontFamily: 'Inter, system-ui' }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Datum({ label, v, accent }) {
  return (
    <div className="flex items-center justify-between">
      <span style={{ color: T.inkLo }}>{label}</span>
      <span style={{ color: accent || T.inkHi }}>{v}</span>
    </div>
  );
}

function DepthLadder({ ticker, center }) {
  // Mock 5 levels each side around `center`
  const asks = [];
  const bids = [];
  for (let i = 0; i < 5; i++) {
    asks.push({ p: center + 1 + i, sz: Math.floor(80 / (i + 1)) + Math.floor(Math.random() * 20) });
    bids.push({ p: center - 1 - i, sz: Math.floor(80 / (i + 1)) + Math.floor(Math.random() * 20) });
  }
  asks.reverse();
  const maxSz = Math.max(...asks.map(a => a.sz), ...bids.map(b => b.sz));
  return (
    <div className="grid grid-cols-2 gap-2 text-[11px]" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
      <div>
        <div className="text-[9px] uppercase tracking-wider mb-1" style={{ color: T.inkDim }}>Bids (Yes)</div>
        {bids.map((b, i) => (
          <div key={i} className="relative flex justify-between px-1.5 py-0.5">
            <div className="absolute inset-y-0 left-0 rounded-sm" style={{ width: `${(b.sz/maxSz)*100}%`, background: 'rgba(61,220,151,0.10)' }} />
            <span className="relative tabular-nums" style={{ color: T.yes }}>{b.p}¢</span>
            <span className="relative tabular-nums" style={{ color: T.inkMid }}>{b.sz}</span>
          </div>
        ))}
      </div>
      <div>
        <div className="text-[9px] uppercase tracking-wider mb-1" style={{ color: T.inkDim }}>Asks (Yes)</div>
        {asks.map((a, i) => (
          <div key={i} className="relative flex justify-between px-1.5 py-0.5">
            <div className="absolute inset-y-0 right-0 rounded-sm" style={{ width: `${(a.sz/maxSz)*100}%`, background: 'rgba(255,122,138,0.10)' }} />
            <span className="relative tabular-nums" style={{ color: T.no }}>{a.p}¢</span>
            <span className="relative tabular-nums" style={{ color: T.inkMid }}>{a.sz}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TheoForm({ s, override, onSubmit }) {
  const [yesC, setYesC] = React.useState(override ? override.yesC : Math.round(s.theo * 100));
  const [conf, setConf] = React.useState(override ? override.conf : 1.0);
  const [reason, setReason] = React.useState(override ? override.reason : '');
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: '110px 110px 1fr auto' }}>
      <Field label="Yes (cents)" suffix="¢">
        <input type="number" value={yesC} onChange={e => setYesC(+e.target.value)}
               className="w-full bg-transparent outline-none tabular-nums text-[13px]"
               style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
      </Field>
      <Field label="Confidence">
        <input type="number" step="0.05" min="0" max="1" value={conf} onChange={e => setConf(+e.target.value)}
               className="w-full bg-transparent outline-none tabular-nums text-[13px]"
               style={{ color: T.inkHi, fontFamily: 'JetBrains Mono, ui-monospace' }} />
      </Field>
      <Field label="Reason (≥4 chars)">
        <input type="text" value={reason} onChange={e => setReason(e.target.value)}
               placeholder="why are you overriding?"
               className="w-full bg-transparent outline-none text-[13px]"
               style={{ color: T.inkHi, fontFamily: 'Inter, system-ui' }} />
      </Field>
      <div className="flex items-end gap-1.5">
        {override && (
          <button onClick={() => onSubmit?.(s.ticker, null)}
                  className="text-[11px] px-2.5 py-1.5 rounded border"
                  style={{ background: T.surface, color: T.inkMid, borderColor: T.border }}>
            clear
          </button>
        )}
        <button onClick={() => onSubmit?.(s.ticker, { yesC, conf, reason })}
                className="text-[11px] font-semibold px-3 py-1.5 rounded border"
                style={{ background: '#1f1a08', color: T.lip, borderColor: '#7a6230' }}>
          {override ? 'update theo' : 'override theo'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, suffix, children }) {
  return (
    <div className="rounded border px-2 py-1" style={{ background: T.surface, borderColor: T.border }}>
      <div className="text-[9px] uppercase tracking-wider" style={{ color: T.inkLo }}>{label}</div>
      <div className="flex items-baseline gap-1">
        {children}
        {suffix && <span className="text-[10px]" style={{ color: T.inkDim }}>{suffix}</span>}
      </div>
    </div>
  );
}

// ── Strike grid header ─────────────────────────────────────────────
function StrikeGridHeader({ density = 'desktop' }) {
  if (density === 'mobile') return null;
  return (
    <div className="grid items-center gap-3 px-3 py-1.5 border-b text-[9px] uppercase tracking-[0.12em]"
         style={{ borderColor: T.border, color: T.inkLo, gridTemplateColumns: '1fr 70px 52px 52px 90px 130px 78px 90px 16px', fontFamily: 'Inter, system-ui' }}>
      <div>Strike</div>
      <div className="text-right">% chance</div>
      <div className="text-center">Yes</div>
      <div className="text-center">No</div>
      <div className="text-right">Position</div>
      <div className="text-right">Resting</div>
      <div className="text-right">LIP</div>
      <div className="text-right">Theo</div>
      <div></div>
    </div>
  );
}

// ── Decision feed ──────────────────────────────────────────────────
function DecisionFeed({ entries, max = 999, compact = false }) {
  const typeMeta = {
    fill:           { fg: T.yes,  label: 'fill' },
    theo_override:  { fg: T.lip,  label: 'theo' },
    order_placed:   { fg: T.info, label: 'order' },
    order_canceled: { fg: T.no,   label: 'cancel' },
    cycle:          { fg: T.inkLo,label: 'cycle' },
  };
  return (
    <div className="font-mono text-[11px]" style={{ fontFamily: 'JetBrains Mono, ui-monospace' }}>
      {entries.slice(0, max).map((e, i) => {
        const m = typeMeta[e.type] || { fg: T.inkMid, label: e.type };
        return (
          <div key={i} className="grid items-baseline gap-2 py-1 border-b"
               style={{ borderColor: T.border + '88', gridTemplateColumns: compact ? '60px 60px 1fr' : '60px 70px 200px 1fr' }}>
            <span style={{ color: T.inkDim }}>{e.ts}</span>
            <span style={{ color: m.fg }}>{m.label}</span>
            {!compact && <span className="truncate" style={{ color: T.inkLo }}>…{e.ticker.slice(-12)}</span>}
            <span style={{ color: T.inkHi }}>{e.summary}</span>
          </div>
        );
      })}
    </div>
  );
}

// expose
Object.assign(window, {
  cls, fmtC, fmtUsd, fmtTimeLeft,
  Pill, PriceChip, StatusBar, StrikeRow, StrikeGridHeader,
  ChanceBar, LipProgress, ExpandedStrike, Section, Datum,
  DepthLadder, TheoForm, Field, DecisionFeed,
});
