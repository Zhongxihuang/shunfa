"""Rate limiter configuration shared across all routers."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

limiter_kwargs = {
    "key_func": get_remote_address,
    "default_limits": [settings.rate_limit_default],
}
if settings.rate_limit_storage_uri:
    limiter_kwargs["storage_uri"] = settings.rate_limit_storage_uri

limiter = Limiter(**limiter_kwargs)
