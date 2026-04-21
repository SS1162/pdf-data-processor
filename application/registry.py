"""Strategy registry — resolves the correct :class:`~core.interfaces.IReportStrategy`
at runtime using the Chain-of-Responsibility pattern.

The registry keeps an **ordered** list of registered strategies and returns the
first one whose :meth:`~core.interfaces.IReportStrategy.can_handle` returns
``True`` for the supplied :class:`~domain.dtos.report_dtos.RawFileData`.

This module is part of the **application layer** and therefore imports only
from ``core/`` and ``domain/dtos/`` — never from ``infrastructure/``.
"""
from __future__ import annotations

from typing import List

from core.exceptions import StrategyNotFoundError
from core.interfaces import ILogger, IReportStrategy
from domain.dtos.report_dtos import RawFileData


class ReportRegistry:
    """Ordered collection of :class:`~core.interfaces.IReportStrategy` instances.

    Strategies are evaluated in registration order; the first match wins.
    New strategies can be added at runtime via :meth:`register`.

    Args:
        strategies: Initial list of concrete strategy instances (injected by
            :class:`~container.Container`).
        logger: An :class:`~core.interfaces.ILogger` instance.

    Example:
        >>> registry = ReportRegistry(strategies=[hebrew_strategy], logger=my_logger)
        >>> strategy = registry.resolve(raw_data)
        >>> strategy.validate(raw_data)
    """

    def __init__(
        self,
        strategies: List[IReportStrategy],
        logger: ILogger,
    ) -> None:
        self._strategies: List[IReportStrategy] = list(strategies)
        self._logger = logger
        self._logger.debug(
            f"ReportRegistry: initialised with "
            f"{[type(s).__name__ for s in self._strategies]}."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, strategy: IReportStrategy) -> None:
        """Append a new strategy to the end of the resolution chain.

        Args:
            strategy: Concrete :class:`~core.interfaces.IReportStrategy` to add.
        """
        self._strategies.append(strategy)
        

    def resolve(self, raw_data: RawFileData) -> IReportStrategy:
        """Return the first strategy that can handle *raw_data*.

        Iterates the registered strategies in order and calls
        :meth:`~core.interfaces.IReportStrategy.can_handle` on each one until
        a match is found (no exceptions are suppressed from ``can_handle``).

        Args:
            raw_data: Extracted PDF data to match against registered strategies.

        Returns:
            The matching :class:`~core.interfaces.IReportStrategy` instance.

        Raises:
            StrategyNotFoundError: When no registered strategy can handle the
                provided data.
        """
        for strategy in self._strategies:
            if strategy.can_handle(raw_data):
                self._logger.info(
                    f"ReportRegistry: strategy matched -> '{type(strategy).__name__}'."
                )
                return strategy

        registered_names = [type(s).__name__ for s in self._strategies]
        raise StrategyNotFoundError(
            f"No registered strategy can handle the provided data. "
            f"Registered: {registered_names}"
        )
