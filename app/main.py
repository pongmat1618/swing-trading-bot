import hmac
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.engine import Engine
from app.models.signal import PriceTick, TradingControl
from app.utils.config import Settings, check_runtime, load_settings
from app.webhook.body_limit import BodyLimit
from app.webhook.tradingview import router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = settings or load_settings()
        check_runtime(config)
        app.state.engine = Engine(config)
        app.state.engine.start()
        try:
            yield
        finally:
            app.state.engine.stop()

    app = FastAPI(title="BTC Swing Bot V1 — PAPER", lifespan=lifespan)
    app.add_middleware(BodyLimit)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Pydantic's default error response can echo the secret from invalid input.
        return JSONResponse(status_code=422, content={"detail": "invalid request schema"})

    def admin(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        expected = request.app.state.engine.settings.admin_token.get_secret_value()
        if not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(401, "invalid admin authentication")

    app.include_router(router)

    @app.get("/health")
    def health(request: Request):
        engine = request.app.state.engine
        alive = bool(engine.thread and engine.thread.is_alive() and engine.healthy)
        return JSONResponse(
            {"mode": "PAPER", "worker_alive": alive}, status_code=200 if alive else 503
        )

    @app.get("/state", dependencies=[Depends(admin)])
    def state(request: Request):
        return request.app.state.engine.state()

    @app.get("/signals/{signal_id}", dependencies=[Depends(admin)])
    def signal_status(signal_id: str, request: Request):
        result = request.app.state.engine.store.signal_status(signal_id)
        if result is None:
            raise HTTPException(404, "signal not found")
        return result

    @app.post("/paper/tick", dependencies=[Depends(admin)])
    def tick(payload: PriceTick, request: Request):
        try:
            return request.app.state.engine.tick(payload.symbol, payload.price)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/admin/trading", dependencies=[Depends(admin)])
    def trading(payload: TradingControl, request: Request):
        return request.app.state.engine.control(payload.enabled)

    return app


app = create_app()
