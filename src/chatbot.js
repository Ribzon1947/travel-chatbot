import { GoogleGenerativeAI } from '@google/generative-ai';
import { config } from './config.js';

// ── Pricing constants ─────────────────────────────────────────────────────────
const HOTEL_COST_PER_ROOM_PER_NIGHT = 2000;
const PEOPLE_PER_ROOM               = 2;
const CAB_COST_FOR_3_DAYS           = 10000;
const MEAL_COST_PER_PERSON_PER_DAY  = 700;
const CAB_COST_PER_DAY              = CAB_COST_FOR_3_DAYS / 3;
const TICKET_COST_PER_PERSON        = 2500;

function calculateTripCost({ num_people, num_days, num_nights }) {
  const nights       = num_nights ?? num_days;
  const rooms        = Math.ceil(num_people / PEOPLE_PER_ROOM);
  const hotelTotal   = rooms * HOTEL_COST_PER_ROOM_PER_NIGHT * nights;
  const cabTotal     = Math.round(CAB_COST_PER_DAY * num_days);
  const mealsTotal   = MEAL_COST_PER_PERSON_PER_DAY * num_people * num_days;
  const ticketTotal  = Math.ceil(num_people * 2500);
  const grandTotal   = hotelTotal + cabTotal + mealsTotal;

  return {
    num_people,
    num_days,
    num_nights:    nights,
    rooms_needed:  rooms,
    hotel_total:   hotelTotal,
    cab_total:     cabTotal,
    meals_total:   mealsTotal,
    ticket_total:  ticketTotal,
    grand_total:   grandTotal,
  };
}

const SYSTEM = `You are a friendly travel cost assistant. You calculate trip expenses using fixed pricing.

Fixed Pricing:
- Hotel room: Rs ${HOTEL_COST_PER_ROOM_PER_NIGHT.toLocaleString()} per room per night
- Room capacity: ${PEOPLE_PER_ROOM} people per room (always round UP for odd numbers)
- Cab: Rs ${CAB_COST_FOR_3_DAYS.toLocaleString()} for 3 days = Rs ${Math.round(CAB_COST_PER_DAY).toLocaleString()} per day (shared by whole group)
- Meals: Rs ${MEAL_COST_PER_PERSON_PER_DAY} per person per day
- Tickets: Rs ${TICKET_COST_PER_PERSON} per person

Instructions:
- When the user mentions number of people and number of days/nights, ALWAYS call the calculate_trip_cost tool immediately — no follow-up questions needed.
- If the user gives both days and nights (e.g. "5 days 4 nights"), use num_days for meals/cab and num_nights for hotel.
- If only days are given, use num_days for everything (num_nights = num_days).
- Show the answer in EXACTLY this format — nothing else:

Rooms needed: X
Hotel cost: Rs Z
Cab cost: Rs Z
Meal cost: Rs Z
Grand Total: Rs Z

OUTPUT RULES — strictly enforced:
- Do NOT add any parentheses, brackets, or extra text after any line.
- Do NOT write multiplication breakdowns.
- Do NOT add notes or any explanation on the same line.
- Do NOT add any line other than the five lines above.
- Just the label, colon, and the Rs amount. Nothing else on any line.
- Use Rs and commas for all amounts.`;

const TOOL_DECLARATION = {
  functionDeclarations: [{
    name: 'calculate_trip_cost',
    description: 'Calculate the complete trip cost breakdown for the given number of people, days, and nights.',
    parameters: {
      type: 'object',
      properties: {
        num_people: {
          type:        'integer',
          description: 'Total number of people travelling (minimum 1)',
        },
        num_days: {
          type:        'integer',
          description: 'Total number of days for the trip (used for meals and cab)',
        },
        num_nights: {
          type:        'integer',
          description: 'Number of nights for hotel stay (if different from num_days; otherwise omit)',
        },
      },
      required: ['num_people', 'num_days'],
    },
  }],
};

const _PAREN_RE = /\s*[\(\[][\s\S]*/;
function stripBreakdowns(text) {
  return text.split('\n').map(l => l.replace(_PAREN_RE, '').trimEnd()).join('\n');
}

export async function chat(message, history) {
  const genAI = new GoogleGenerativeAI(config.googleAiKey);
  const model = genAI.getGenerativeModel({
    model:             config.agentModel,
    systemInstruction: SYSTEM,
    tools:             [TOOL_DECLARATION],
  });

  const chatHistory = history.map(m => ({
    role:  m.role === 'user' ? 'user' : 'model',
    parts: [{ text: m.content }],
  }));

  const chatSession = model.startChat({ history: chatHistory });

  let result = await chatSession.sendMessage(message);

  // Agentic loop: keep going while the model wants to call functions
  while (true) {
    const candidate = result.response.candidates?.[0];
    const parts     = candidate?.content?.parts ?? [];

    const fnCalls = parts.filter(p => p.functionCall);
    if (!fnCalls.length) {
      const text = parts.filter(p => p.text).map(p => p.text).join('\n').trim();
      return stripBreakdowns(text);
    }

    const fnResponses = fnCalls.map(p => {
      const { name, args } = p.functionCall;
      const response = name === 'calculate_trip_cost'
        ? calculateTripCost(args)
        : { error: `Unknown function: ${name}` };
      return { functionResponse: { name, response } };
    });

    result = await chatSession.sendMessage(fnResponses);
  }
}
