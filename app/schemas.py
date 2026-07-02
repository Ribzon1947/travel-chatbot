from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    from_location: str = ""
    to_location: str = "Default"


class ChatResponse(BaseModel):
    reply: str


class DestinationPricing(BaseModel):
    hotel_cost_per_room_per_night: int
    people_per_room: int
    cab_cost_per_day: int
    meal_cost_per_person_per_day: int
    ticket_cost_per_person: int


class DestinationCreate(BaseModel):
    name: str
    pricing: DestinationPricing
