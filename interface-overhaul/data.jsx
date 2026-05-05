// Shared mock data + design tokens for the lipmm dashboard redesign.
// All values reflect the real backend data shapes documented in the brief.

const TOKENS = {
  // Surfaces (slate-950 family, slightly desaturated)
  bgBase:        '#070b14',
  bgRaise:       '#0c1320',
  surface:       '#0f1623',
  surface2:      '#161f30',
  surface3:      '#1d2841',
  border:        '#1e2a40',
  borderStrong:  '#2a3a55',
  // Ink
  inkHi:         '#e6edf7',
  inkMid:        '#a6b1c8',
  inkLo:         '#6b7791',
  inkDim:        '#4a556d',
  // Semantic
  yes:           '#3ddc97',   // long / Yes / positive
  yesDim:        '#1f6e54',
  no:            '#ff7a8a',   // short / No / negative
  noDim:         '#7a3340',
  info:          '#5fb1ff',
  warn:          '#f0b86c',
  lip:           '#e6c065',   // LIP gold
  lipDim:        '#5a4923',
  danger:        '#ff5562',
  dangerDim:     '#5a1820',
  // Accent for live/connected
  live:          '#3ddc97',
};

// 8 strikes of KXISMPMI-26MAY (ISM Manufacturing PMI ≥ N this month)
const STRIKES = [
  { ticker: 'KXISMPMI-26MAY-49', threshold: 49, label: 'At least 49',
    yesC: 92, noC: 9,  spread: 1, theo: 0.91, ourTheo: null,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 312 } },

  { ticker: 'KXISMPMI-26MAY-50', threshold: 50, label: 'At least 50',
    yesC: 78, noC: 23, spread: 1, theo: 0.78, ourTheo: 0.79,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [
      { id: 'ord-50-b', side: 'bid', priceC: 77, size: 5, ageS: 142 },
      { id: 'ord-50-a', side: 'ask', priceC: 80, size: 5, ageS: 142 },
    ],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 188 } },

  { ticker: 'KXISMPMI-26MAY-51', threshold: 51, label: 'At least 51',
    yesC: 49, noC: 52, spread: 3, theo: 0.50, ourTheo: 0.50,
    pos: +2, avgC: 49, realized: 0,    fees: 0.04,
    resting: [
      { id: 'ord-51-b', side: 'bid', priceC: 48, size: 8, ageS: 38, recentFill: true },
      { id: 'ord-51-a', side: 'ask', priceC: 52, size: 8, ageS: 38 },
    ],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 76 } },

  { ticker: 'KXISMPMI-26MAY-52', threshold: 52, label: 'At least 52',
    yesC: 28, noC: 73, spread: 1, theo: 0.27, ourTheo: null,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [
      { id: 'ord-52-b', side: 'bid', priceC: 26, size: 5, ageS: 612 },
      { id: 'ord-52-a', side: 'ask', priceC: 29, size: 5, ageS: 612 },
    ],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 41 } },

  { ticker: 'KXISMPMI-26MAY-53', threshold: 53, label: 'At least 53',
    yesC: 12, noC: 89, spread: 1, theo: 0.11, ourTheo: null,
    pos: -3, avgC: 13, realized: 0.20, fees: 0.11,
    resting: [
      { id: 'ord-53-a', side: 'ask', priceC: 13, size: 5, ageS: 88 },
    ],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 22 } },

  { ticker: 'KXISMPMI-26MAY-54', threshold: 54, label: 'At least 54',
    yesC: 5,  noC: 96, spread: 1, theo: 0.05, ourTheo: null,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 8  } },

  { ticker: 'KXISMPMI-26MAY-55', threshold: 55, label: 'At least 55',
    yesC: 2,  noC: 99, spread: 1, theo: 0.02, ourTheo: null,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 0  } },

  { ticker: 'KXISMPMI-26MAY-56', threshold: 56, label: 'At least 56',
    yesC: 1,  noC: 99, spread: 1, theo: 0.01, ourTheo: null,
    pos: 0,  avgC: 0,  realized: 0,    fees: 0,
    resting: [],
    lip: { reward: 125, target: 1000, discountBps: 2500, endTs: 1778365599, timeLeftS: 442800, filled: 0  } },
];

const ACCOUNT = {
  cash: 99.17,
  port: 1.95,
  pnl:  +0.43,
  fees: 0.21,
  tabs: 1,
  killState: 'off',     // off | killed | armed
  globalPaused: false,
  pausedTickers: [],
  pausedSides: [],
  knobOverrides: { min_theo_confidence: 0.65 },
  sideLocks: [],
  theoOverrides: [
    { ticker: 'KXISMPMI-26MAY-50', yesC: 79, conf: 1.0, reason: 'fading prelim PMI hint',     setAt: '14:02:11', actor: 'op' },
    { ticker: 'KXISMPMI-26MAY-51', yesC: 50, conf: 1.0, reason: 'centered on consensus',      setAt: '14:02:34', actor: 'op' },
  ],
  version: 142,
};

const FEED = [
  { ts: '14:02:34', type: 'theo_override',  ticker: 'KXISMPMI-26MAY-51', summary: 'theo set 50¢ — "centered on consensus"' },
  { ts: '14:02:11', type: 'theo_override',  ticker: 'KXISMPMI-26MAY-50', summary: 'theo set 79¢ — "fading prelim PMI hint"' },
  { ts: '14:01:58', type: 'fill',           ticker: 'KXISMPMI-26MAY-51', summary: 'fill bid @ 48¢ × 2  +2 Y' },
  { ts: '14:01:42', type: 'order_placed',   ticker: 'KXISMPMI-26MAY-51', summary: 'place bid 48¢ × 8 / ask 52¢ × 8' },
  { ts: '14:01:33', type: 'order_canceled', ticker: 'KXISMPMI-26MAY-51', summary: 'cancel old quotes (theo move)' },
  { ts: '14:01:12', type: 'cycle',          ticker: '*',                 summary: 'cycle 2,847 — 8 strikes evaluated, 5 quoting' },
  { ts: '14:00:48', type: 'fill',           ticker: 'KXISMPMI-26MAY-53', summary: 'fill ask @ 13¢ × 3  −3 N  (realized +$0.20)' },
];

window.TOKENS = TOKENS;
window.STRIKES = STRIKES;
window.ACCOUNT = ACCOUNT;
window.FEED = FEED;
