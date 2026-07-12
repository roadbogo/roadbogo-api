from pydantic import BaseModel


class RouteSummary(BaseModel):
    id: str
    name: str
    status: str
