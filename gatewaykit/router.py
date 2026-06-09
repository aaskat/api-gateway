"""Router: maps a request path to a RouteConfig by longest-prefix match."""

from gatewaykit.config import RouteConfig


class Router:
    """Longest-prefix, segment-aware path router."""

    def __init__(self, routes: list[RouteConfig]):
        # Sort by path length desc so the first matching route is the longest prefix.
        self._routes = sorted(routes, key=lambda r: len(r.path), reverse=True)

    def match(self, path: str) -> RouteConfig | None:
        for route in self._routes:
            if path == route.path or path.startswith(route.path + "/"):
                return route
        return None
