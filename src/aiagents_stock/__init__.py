"""aiagents-stock modular package."""

from src.aiagents_stock.core.encoding import configure_console_encoding
from src.aiagents_stock.infrastructure.network.proxy import disable_proxy_env


configure_console_encoding()
disable_proxy_env()
