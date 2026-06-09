"""Entrypoint: python -m gatewaykit [config.yaml]

The config path comes from (in priority order): a command-line argument, the
GATEWAYKIT_CONFIG env var, a .env file, or the default "gateway.yaml". The
config is loaded and validated up front, failing fast with a clear message.
"""

import sys

from gatewaykit.config import ConfigError, load_config
from gatewaykit.server import GatewayServer
from gatewaykit.settings import Settings


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else Settings().config
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(1)
    GatewayServer(config).serve_forever()


if __name__ == "__main__":
    main()
