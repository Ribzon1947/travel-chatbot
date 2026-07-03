import asyncio
import re
from google import genai
from google.genai import types

from app.config import get_settings
from app.pricing import calculate_trip_cost, compare_destinations, get_destination_pricing, calculate_multi_city_trip

_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="calculate_trip_cost",
        description=(
            "Calculate the complete trip cost breakdown for the given origin, destination, number of people, and days. "
            "Always call this before giving any cost figures."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "from_location": types.Schema(
                    type=types.Type.STRING,
                    description="Origin place or city for the route.",
                ),
                "destination": types.Schema(
                    type=types.Type.STRING,
                    description="Destination place or city.",
                ),
                "num_people": types.Schema(
                    type=types.Type.INTEGER,
                    description="Total number of people travelling (minimum 1)",
                ),
                "num_days": types.Schema(
                    type=types.Type.INTEGER,
                    description="Total number of calendar days for the trip",
                ),
                "num_nights": types.Schema(
                    type=types.Type.INTEGER,
                    description=(
                        "Total number of nights for the trip. "
                        "If equal to num_days, hotel and meals are charged at full rate. "
                        "If less than num_days (days > nights), whole day+night pairs are full rate "
                        "and the remaining day(s) are charged at half rate for hotel and meals. "
                        "Omit only if nights were not mentioned by the user."
                    ),
                ),
            },
            required=["num_people", "num_days", "destination"],
        ),
    ),
    types.FunctionDeclaration(
        name="compare_destinations",
        description=(
            "Compare trip costs across multiple destinations from a given origin for the same group size and duration. "
            "Call this when the user asks to compare two or more destinations."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "from_location": types.Schema(
                    type=types.Type.STRING,
                    description="Origin place or city for the comparison.",
                ),
                "destinations": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="List of destination names to compare (e.g. ['Goa', 'Manali', 'Shimla'])",
                ),
                "num_people": types.Schema(
                    type=types.Type.INTEGER,
                    description="Total number of people travelling (minimum 1)",
                ),
                "num_days": types.Schema(
                    type=types.Type.INTEGER,
                    description="Total number of calendar days for the trip",
                ),
                "num_nights": types.Schema(
                    type=types.Type.INTEGER,
                    description=(
                        "Total number of nights. Omit if nights were not mentioned by the user."
                    ),
                ),
            },
            required=["destinations", "num_people", "num_days"],
        ),
    ),
])

_PAREN_RE = re.compile(r'\s*[\(\[].*', re.DOTALL)

_client: genai.Client | None = None


def _build_system_prompt(from_loc: str, to_loc: str, p: dict) -> str:
    route = f"from {from_loc} to {to_loc}" if from_loc else f"to {to_loc}"
    return f"""You are a friendly travel cost assistant. You calculate trip expenses for a trip {route}.

Fixed Pricing for {to_loc}:
- Hotel room: Rs {p['hotel_cost_per_room_per_night']:,} per room per night
- Room capacity: {p['people_per_room']} people per room (always round UP for odd numbers)
- Cab: Rs {p['cab_cost_per_day']:,} per day (shared by whole group)
- Meals: Rs {p['meal_cost_per_person_per_day']} per person per day
- Tickets: Rs {p['ticket_cost_per_person']:,} per person

Billing rules for hotel and meals:
- Days == Nights (or only days given): each day/night counts as ONE full night — full rate applies.
- Days > Nights: each day+night pair = 1 whole charge; remaining day(s) = HALF rate for hotel and meals.
- Cab cost is always charged per calendar day regardless of nights.

Instructions:
- When the user mentions number of people and days (and optionally nights), ALWAYS call the calculate_trip_cost tool immediately — no follow-up questions needed.
- Pass num_nights to the tool whenever the user mentions nights separately from days.
- When the user asks to compare destinations, call compare_destinations with all mentioned destination names, the people count, the days count, and the origin.
- Show a single-destination answer in EXACTLY this format — nothing else:

Destination: {to_loc}
Rooms needed: X
Hotel cost: Rs Z
Cab cost: Rs Z
Meal cost: Rs Z
Ticket cost: Rs Z
Grand Total: Rs Z

- Show a comparison answer in EXACTLY this format — a markdown table with destinations as columns (cheapest destination first/leftmost), then a Cheapest line:

Comparison: X people, Y days

| Category     | Destination A | Destination B |
|:-------------|:-------------|:-------------|
| Rooms needed | X            | X            |
| Hotel cost   | Rs Z         | Rs Z         |
| Cab cost     | Rs Z         | Rs Z         |
| Meal cost    | Rs Z         | Rs Z         |
| Ticket cost  | Rs Z         | Rs Z         |
| Total        | Rs Z         | Rs Z         |

Cheapest: A at Rs Z

- Show a multi-city answer in EXACTLY this format — nothing else:

Multi-City Trip: X destinations, Y total days
Hotel total: Rs Z
Cab total: Rs Z
Meals total: Rs Z
Ticket total: Rs Z
Grand Total: Rs Z

OUTPUT RULES — strictly enforced:
- Do NOT add any parentheses, brackets, or extra text after any line.
- Do NOT write multiplication breakdowns.
- Do NOT add notes or explanation on the same line.
- Use Rs and commas for all amounts.
"""


def _strip_breakdowns(text: str) -> str:
    return "\n".join(_PAREN_RE.sub('', line).rstrip() for line in text.splitlines())


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        key = get_settings().google_ai_key
        if not key:
            raise RuntimeError("GOOGLE_AI_KEY is not configured. Add it in Render → Environment.")
        _client = genai.Client(api_key=key)
    return _client


def _sync_chat(message: str, history: list[dict], from_loc: str, to_loc: str) -> str:
    client   = _get_client()
    settings = get_settings()
    pricing  = get_destination_pricing(to_loc)
    system   = _build_system_prompt(from_loc, to_loc, pricing)

    contents: list[types.Content] = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    config = types.GenerateContentConfig(system_instruction=system, tools=[_TOOL])

    while True:
        response = client.models.generate_content(
            model=settings.agent_model,
            contents=contents,
            config=config,
        )

        if not response.candidates or not response.candidates[0].content:
            return "Sorry, I couldn't generate a response. Please try again."
        parts      = response.candidates[0].content.parts or []
        text_parts = [p.text          for p in parts if p.text]
        fn_calls   = [p.function_call for p in parts if p.function_call]

        if not fn_calls:
            return _strip_breakdowns("\n".join(text_parts).strip())

        contents.append(types.Content(role="model", parts=parts))

        result_parts = []
        for fc in fn_calls:
            try:
                if fc.name == "calculate_trip_cost":
                    result = calculate_trip_cost(**fc.args, destination=to_loc)
                elif fc.name == "compare_destinations":
                    result = {"comparisons": compare_destinations(**fc.args)}
                # 3. ADDED THE NEW ELIF BLOCK TO EXECUTE THE TOOL
                elif fc.name == "calculate_multi_city_trip":
                    result = calculate_multi_city_trip(**fc.args)
                else:
                    result = {"error": f"Unknown function: {fc.name}"}
            except (TypeError, ValueError, KeyError) as e:
                result = {"error": f"Tool call failed: {e}"}
            result_parts.append(types.Part(
                function_response=types.FunctionResponse(name=fc.name, response=result)
            ))

        contents.append(types.Content(role="user", parts=result_parts))


async def chat(message: str, history: list[dict], from_loc: str = "", to_loc: str = "Default") -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_chat, message, history, from_loc, to_loc)