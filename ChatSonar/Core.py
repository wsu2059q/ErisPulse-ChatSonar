from ErisPulse.Core.Bases import BaseModule
from ErisPulse import sdk

from .Collector import Collector
from .Analyzer import Analyzer
from .Visualizer import Visualizer
from .Commands import Commands


class Main(BaseModule):
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar")
        self.storage = sdk.storage
        self.config = self._load_config()

        self.collector = Collector(sdk, self.config)
        self.analyzer = Analyzer(sdk, self.config)
        self.visualizer = Visualizer(sdk, self.config)
        self.commands = Commands(sdk, self.collector, self.analyzer,
                                 self.visualizer, self.config)

    @staticmethod
    def get_load_strategy():
        from ErisPulse.loaders import ModuleLoadStrategy
        return ModuleLoadStrategy(
            lazy_load=False,
            priority=50,
        )

    async def on_load(self, event):
        from ErisPulse.Core.Event import message

        @message.on_message(priority=100)
        async def collect_handler(evt):
            await self.collector.on_message(evt)

        self._message_handler = collect_handler

        self.commands.register()
        self._register_routes()

        await self.collector.start()

        self.logger.info("ChatSonar 模块已加载")

    async def on_unload(self, event):
        await self.collector.stop()

        from ErisPulse.Core.Event import message
        if hasattr(self, "_message_handler"):
            message.unregister(self._message_handler)

        self.sdk.router.unregister_all_by_namespace("ChatSonar")

        self.logger.info("ChatSonar 模块已卸载")
        return True

    def _register_routes(self):
        from fastapi import Request
        from fastapi.responses import Response

        async def sonar_page(request: Request):
            html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>ChatSonar</title>
    <style>
        body { background: #0a0a1a; color: #aac; font-family: sans-serif; margin: 40px; }
        h1 { color: #00ff88; }
        a { color: #00bbff; }
        .api-list { background: #111; padding: 20px; border-radius: 8px; }
        .api-list code { color: #00ff88; }
    </style>
</head>
<body>
    <h1>ChatSonar API</h1>
    <div class="api-list">
        <p><code>GET /ChatSonar/data</code> - JSON 距离矩阵</p>
        <p><code>GET /ChatSonar/islands</code> - 岛屿数据</p>
        <p><code>GET /ChatSonar/scopes</code> - 所有监测范围</p>
    </div>
</body>
</html>"""
            return Response(content=html, media_type="text/html")

        async def get_scopes(request: Request):
            scopes = self.collector.get_all_scopes()
            return {"scopes": list(scopes)}

        async def get_data(request: Request):
            scope = request.query_params.get("scope")
            if not scope:
                return {"error": "scope parameter required"}
            data = self.analyzer.compute_distance_matrix(scope)
            if not data:
                return {"error": "no data"}
            return {
                "users": data["users"],
                "matrix": data["matrix"],
                "timestamp": data["timestamp"],
            }

        async def get_islands(request: Request):
            scope = request.query_params.get("scope")
            if not scope:
                return {"error": "scope parameter required"}
            data = self.analyzer.compute_distance_matrix(scope)
            if not data:
                return {"error": "no data"}
            islands = self.analyzer.detect_islands(scope, data)
            return {"islands": islands}

        self.sdk.router.register_http_route(
            module_name="ChatSonar",
            path="/",
            handler=sonar_page,
            methods=["GET"],
        )
        self.sdk.router.register_http_route(
            module_name="ChatSonar",
            path="/scopes",
            handler=get_scopes,
            methods=["GET"],
        )
        self.sdk.router.register_http_route(
            module_name="ChatSonar",
            path="/data",
            handler=get_data,
            methods=["GET"],
        )
        self.sdk.router.register_http_route(
            module_name="ChatSonar",
            path="/islands",
            handler=get_islands,
            methods=["GET"],
        )

    def _load_config(self):
        config = sdk.config.getConfig("ChatSonar")
        if not config:
            default_config = {
                "min_messages": 10,
                "update_interval": 3600,
                "distance_threshold": 0.6,
                "top_vocab_count": 100,
                "cache_enabled": True,
                "density_bandwidth": 0.15,
                "cooccur_window": 300,
                "radar_distance_scale": 1.2,
                "radar_max_radius": 1.1,
                "weights": {
                    "timing": 0.20,
                    "emoji": 0.15,
                    "vocab": 0.20,
                    "interaction": 0.30,
                    "cooccurrence": 0.15,
                },
            }
            sdk.config.setConfig("ChatSonar", default_config)
            return default_config
        return config
