from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    success: Literal[True]
    data: DataT | None = None
    message: str | None = None
    trace_id: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    success: Literal[False]
    error: ErrorDetail
    trace_id: str
