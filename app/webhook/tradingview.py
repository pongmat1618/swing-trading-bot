import hmac
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request

from app.engine import validate_scope
from app.models.signal import Signal, WebhookSignal
from app.storage import QueueFull, SignalConflict

router = APIRouter()


@router.post("/webhook/tradingview", status_code=202)
def receive_signal(
    payload: WebhookSignal,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
):
    engine = request.app.state.engine
    supplied = payload.secret.get_secret_value() if payload.secret else ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization[7:]
    if not hmac.compare_digest(
        supplied.encode(), engine.settings.webhook_secret.get_secret_value().encode()
    ):
        raise HTTPException(401, "invalid webhook authentication")
    signal = Signal.model_validate(payload.model_dump())
    try:
        validate_scope(signal, engine.settings)
        status, duplicate = engine.store.enqueue(signal, engine.settings.queue_limit)
    except SignalConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(503, str(exc)) from exc
    except sqlite3.OperationalError as exc:
        raise HTTPException(503, "database busy; retry the same signal_id") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    engine.wake_event.set()
    return {"signal_id": signal.signal_id, "status": status, "duplicate": duplicate}
