# Where2Go 🥂

A Telegram bot that helps a group of friends agree on where to go out. Add it to the group chat, everyone taps what they feel like, and the bot ranks the places that fit the whole group.

<img width="340" height="669" alt="demo" src="https://github.com/user-attachments/assets/a3d40e6c-43b4-4975-a15f-6568cae8c6c1" />
<img width="1290" height="2796" alt="image" src="https://github.com/user-attachments/assets/1d7c9dc4-aca7-4d8f-8e1c-167e8e3e5a88" />


## The problem

Picking a place for yourself is easy. Picking one for five friends with different tastes, budgets and moods usually ends with "I don't mind, you choose".

Where2Go turns that conversation into a one-minute vote and a ranked shortlist.

## How it works

1. Someone sends `/vote` in the group chat.
2. The bot posts one message with buttons in four categories: cuisine, drinks, budget per person and vibe. If the database covers more than one city, a city category appears as well.
3. Everyone taps as many options as they like. A second tap removes the vote, and the counters on the buttons update live.
4. Anyone presses "Done" and the bot replies with the top places for this group, each with a short description.

### Matching

Every place in the database is scored against the group's votes:

| Criterion | Weight | How it is counted |
|---|---|---|
| Cuisine | 3.0 | votes for each cuisine the place serves |
| Budget | 2.5 | full weight for the exact price band, half for the neighbouring one |
| Drinks | 2.0 | votes multiplied by how strong the place is in that drink (0 to 3) |
| Vibe | 1.5 | votes for each matching atmosphere |

The scoring is simple and transparent on purpose: the group can see why a place won. Weights, categories and the size of the shortlist live in `config.py`.

## From manual tagging to AI

**Prototype.** The first version worked only on the matcher above. Every place had to be tagged by hand in a strict seven-field format (`/add Название | Район | кухни | напитки | чек | атмосфера | описание`). That was fine for a handful of favourite spots in one city, but each new place, and especially each new city, meant more manual tagging.

**AI scout.** The `/discover` command removes that step. A curator describes what the group is after in plain words, for example `/discover wine bar with snacks` or `/discover Berlin raves`, and an AI agent:

- works out the city from the phrase (Almaty if none is mentioned)
- searches the web for real places that match and checks they are still open
- returns each candidate already tagged in the bot's own schema: cuisines, drink scores, budget band, vibes, a short summary
- marks how confident it is that the data is current

The curator adds a candidate to the database or skips it with one tap. A new city needs no preparation at all, and the group vote keeps working on the same scoring as before.

## Why not just ask an AI chat?

An AI chat answers one person. Where2Go lives where the decision is actually made, in the group chat:

- everyone votes in the same message, and every vote weighs the same
- the result reflects the whole group, not the person who typed the question
- the shortlist comes from a base of places the group has approved, so there are no invented venues

## Commands

| Command | Who | What it does |
|---|---|---|
| `/vote` | everyone | starts a group vote |
| `/list` | everyone | shows the places in the database |
| `/discover <phrase>` | curators | AI search for new places, in any city |
| `/add <fields>` | curators | adds a place by hand |
| `/del <id>` | curators | removes a place |
| `/id` | everyone | shows chat and user IDs for access setup |

## Tech stack

- Python, [aiogram 3](https://docs.aiogram.dev/) (async Telegram Bot API, long polling)
- PostgreSQL via psycopg 3, tags stored as JSONB
- Anthropic API: Claude Haiku with the web search tool for `/discover`
- Deployed on Railway as a worker process

## Project structure

```
bot.py        commands, voting keyboard, access control
matcher.py    weighted scoring of places against votes
discover.py   AI agent: web search and automatic tagging
parse.py      parser for the manual /add format
db.py         PostgreSQL storage
config.py     categories, weights, model and limits
```

## Running it

```bash
git clone https://github.com/mfkhakimova-boop/where2go
cd where2go
pip install -r requirements.txt
python bot.py
```

Environment variables (a local `.env` file works too):

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_TOKEN` | yes | bot token from @BotFather |
| `DATABASE_URL` | yes | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | for `/discover` | key for the AI scout |
| `ALLOWED_CHATS` | no | comma-separated chat IDs the bot answers in; empty means any chat |
| `ADMINS` | no | comma-separated user IDs of curators; empty means anyone can edit the base |

## What's next

- Open `/discover` to every member of the chat, not only curators
- Let people describe what they want in free text instead of buttons
- Keep votes across restarts (they are held in memory now)

## Author

Munira Khakimova, systems analyst working on mobile products.
telegram @thatsmoony
linkedin https://www.linkedin.com/in/munira-khakimova-39a586237/
