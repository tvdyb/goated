"""CME options chain and futures settlement data ingest.

F4-ACT-02: closes GAP-046 (CME ZS option-chain ingest),
GAP-047 (put-call parity prune), GAP-063 (CME EOD settlements pull).

Modules:
  options_chain   — EOD options chain puller for ZS (soybean futures options).
  futures_settle  — Daily settlement price puller.
  expiry_calendar — CBOT options expiry calendar.
"""
