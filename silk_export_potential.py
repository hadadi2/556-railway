"""Compatibility entry point; the unverified Comtrade approximation is retired.

Prefer export_potential.app for standalone use. No platform imports or database.
"""
from export_potential.routes import mount
__all__ = ['mount']
