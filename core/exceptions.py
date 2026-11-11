class GodswillError(Exception):
    """Base for all platform errors."""


class ConfigurationError(GodswillError):
    pass


class DatabaseError(GodswillError):
    pass


class MarketDataError(GodswillError):
    pass


class MT5ConnectionError(GodswillError):
    pass


class RiskRejected(GodswillError):
    pass


class ExecutionError(GodswillError):
    pass