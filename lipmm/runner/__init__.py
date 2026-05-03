"""The cycle orchestrator.

Wires TheoRegistry + QuotingStrategy + OrderManager + ExchangeClient into a
running bot loop. Doesn't know anything about specific markets — receives
all the dependencies via constructor injection.

A typical bot startup script looks like:

    from lipmm.theo import TheoRegistry
    from lipmm.theo.providers.gbm_commodity import GbmCommodityTheo, ...
    from lipmm.quoting.strategies.default import DefaultLIPQuoting
    from lipmm.execution import OrderManager
    from lipmm.runner import LIPRunner, RunnerConfig
    from my_market.kalshi_adapter import KalshiExchangeAdapter

    registry = TheoRegistry()
    registry.register(GbmCommodityTheo(...))
    runner = LIPRunner(
        config=RunnerConfig(...),
        theo_registry=registry,
        strategy=DefaultLIPQuoting(),
        order_manager=OrderManager(),
        exchange=KalshiExchangeAdapter(...),
        ticker_source=...,
    )
    await runner.run()
"""

from lipmm.runner.runner import LIPRunner, RunnerConfig, TickerSource

__all__ = ["LIPRunner", "RunnerConfig", "TickerSource"]
