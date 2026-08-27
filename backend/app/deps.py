from typing import Annotated, cast

from fastapi import Depends, Request

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_request_id(request: Request) -> str:
    return cast(str, request.state.request_id)
