from fastapi.responses import FileResponse


def register_routes(app) -> None:
    @app.get("/")
    async def home() -> FileResponse:
        return FileResponse("web/templates/index.html")
