# Toronto Weekend Companion

## Overview

Toronto Weekend Companion is a small conversational AI application for planning practical Toronto weekend outings. The assistant, Milo, helps users check weather, find local places and activities, and turn basic constraints into a simple plan.

## Chat Personality

Milo is calm, friendly, concise, practical, and budget-aware. Milo prefers useful recommendations over long explanations and is careful not to invent weather details or place data.

## Services

### Service 1: Weather API

The weather service uses the free Open-Meteo geocoding and forecast APIs. It accepts a city name, defaults to Toronto, resolves the location, calls the forecast endpoint, and keeps only useful fields such as resolved location, current temperature, apparent temperature, condition, precipitation probability, wind, forecast dates, and indoor/outdoor guidance.

The raw API JSON is not shown to the user. If the API times out, a location cannot be resolved, or the response is malformed, the tool returns a small structured error for the model to explain calmly.

### Service 2: Semantic Place Search

The place search service uses a curated CSV dataset of Toronto places and activities at `assignment_chat/data/toronto_places.csv`. The dataset includes museums, galleries, markets, parks, libraries, cultural centres, waterfront destinations, rainy-day activities, low-cost activities, and food-oriented destinations.

Searchable fields are `name`, `category`, `description`, `area`, `indoor_outdoor`, and `estimated_cost`. Each embedding document is constructed as:

```text
Name: ...
Category: ...
Description: ...
Area: ...
Setting: ...
Estimated cost: ...
```

The embedding model is `text-embedding-3-small`, matching the course examples. The ChromaDB collection name is `toronto_places`, stored with `chromadb.PersistentClient` at `assignment_chat/data/chroma_db`. The app reads the persisted collection, so evaluators normally do not need to regenerate embeddings. The search tool returns the top three results by default with structured fields: name, category, area, setting, estimated cost, description, and website.

Semantic search was chosen because users often ask by intent, such as "quiet indoor art activity downtown," not by exact place name.

### Service 3: Weekend Planning Function

The planning tool is a pure Python function exposed through LangChain tool calling. Inputs are:

- `budget_per_person`
- `available_hours`
- `number_of_people`
- `preference`
- `weather_condition`

The function validates negative budgets, zero or negative hours, invalid group sizes, missing preferences, and unknown weather. It returns structured planning fields such as total budget, budget level, recommended number of stops, indoor priority, time allocation, and planning notes. Milo uses that structure and the conversation context to write the final answer.

## Architecture

The app follows the same simple LangGraph tool loop used in the course examples.

```text
Gradio chat
  -> deterministic guardrail check
  -> LangGraph LLM node with Milo system prompt
  -> tool node when the model requests a tool
  -> LLM synthesis
  -> user response
```

The graph binds all three tools: weather, place search, and weekend planning. A small maximum LLM-call limit prevents runaway tool loops.

## Conversation Memory

Gradio provides the active conversation history to `assignment_chat.chat.assignment_chat`. The app converts prior user and assistant turns into LangChain `HumanMessage` and `AIMessage` objects and sends them back into the graph on each turn. No long-term memory is stored, and no message truncation is currently applied.

## Guardrails

The app uses both prompt-level and code-level safeguards. `guardrails.py` runs before the LLM and blocks two categories:

- system-prompt or internal-instruction extraction/modification attempts;
- restricted topics: cats, dogs, horoscopes, zodiac signs, horoscope-style astrology, and Taylor Swift.

The deterministic pre-check prevents obvious unsafe or out-of-scope requests from reaching the model. The system prompt also instructs Milo not to reveal hidden instructions or answer restricted topics.

## Project Structure

- `app.py`: Gradio launch entry point.
- `chat.py`: LangGraph setup, Gradio history conversion, guardrail routing, and chat function.
- `prompts.py`: Milo system prompt.
- `guardrails.py`: deterministic input checks.
- `tools_weather.py`: Open-Meteo API service.
- `tools_places.py`: ChromaDB semantic search service.
- `tools_planner.py`: pure Python planning tool.
- `build_embeddings.py`: script for rebuilding the persisted Chroma collection.
- `data/toronto_places.csv`: curated Toronto places dataset.
- `data/chroma_db/`: persisted ChromaDB collection.

## Embedding Build Process

To regenerate embeddings:

```bash
cd 05_src
python -m assignment_chat.build_embeddings
```

This is normally unnecessary because the persistent database is included. Regeneration requires the same course OpenAI environment configuration used elsewhere in the repository.

## How to Run

```bash
cd 05_src
python -m assignment_chat.app
```

The app uses the existing course environment variables for OpenAI access, loaded from `.env` and `.secrets` when present. Secret values are not stored in this project folder.

## Example Questions

- Weather: "What is the weather in Toronto?"
- Weather and activity fit: "Is Toronto suitable for an outdoor activity today?"
- Place search: "Find a quiet indoor art activity downtown."
- Place search: "Suggest a low-cost place for a rainy afternoon."
- Planning: "I have three hours and a budget of $40 per person. Make a plan for two people."
- Memory: "I prefer indoor activities." Then: "My budget is $30 per person." Then: "I would like to stay downtown." Then: "Now suggest something and make a plan using what I told you."

## Testing

The implementation was checked with direct tool calls, guardrail checks, embedding build checks, import checks, and app launch checks. Test coverage included:

- basic chat import and launch readiness;
- weather requests for Toronto and an invalid location;
- semantic queries for indoor art, low-cost rainy-day activities, waterfront destinations, and food-oriented places;
- planner validation for normal inputs, zero budget, negative budget, zero hours, invalid people, and missing preference;
- memory path through Gradio history conversion;
- guardrail blocks for prompt extraction, instruction override, restricted topics, and normal non-matches containing the word "prompt."

## Design Decisions

The project uses three small services so each assignment requirement is visible and easy to assess. `chromadb.PersistentClient` was chosen because the assignment asks for file persistence without a Docker database. The dataset is intentionally small so it stays easy to inspect, commit, and regenerate.

The third service is a pure function-calling planner instead of MCP or agentic web search because the assignment does not need external write actions or broad web retrieval. No booking, purchasing, or account actions are included. No new libraries were introduced; the implementation uses packages already present in the course environment.

## Limitations

- Weather depends on internet access and Open-Meteo availability.
- Place search uses a small local dataset, not a complete city guide.
- Conversation memory lasts only for the active Gradio session.
- Planning logic is simplified and should be treated as a practical framework, not a full itinerary engine.
- The app is not a booking, ticketing, payment, or transaction system.
