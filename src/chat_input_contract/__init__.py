"""Offline contracts for chat preprocessing. Capture is an optional dependency."""
from .core import compare_snapshots, validate_snapshot
from .errors import ContractError

__version__ = '0.2.0'
__all__ = ['compare_snapshots', 'validate_snapshot', 'ContractError']
