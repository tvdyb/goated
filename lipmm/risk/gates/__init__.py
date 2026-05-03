"""Concrete RiskGate implementations.

One file per gate. The framework's core never has to change to add a new
gate — it just needs to satisfy the RiskGate protocol.

Conventions:
  - Gate class name suffixed with `Gate` (e.g. `MaxNotionalPerSideGate`).
  - Constructor takes plain config (not a separate Config dataclass —
    gates are simple enough to not warrant the indirection).
  - `name` attribute is a class-level constant (not constructor-set).
  - Gates are free-standing instances; multiple instances of the same gate
    type with different configs can coexist in one registry.
"""
