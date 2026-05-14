"""Initialization/bootstrap package.

Holds startup configuration, seed scripts, and generated schema metadata.
"""

from init.config import Config
from init.seed_users import seed_default_admin

__all__ = ["Config", "seed_default_admin"]
