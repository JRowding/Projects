# Party Card Game

A playable MVP of a private, Cards Against Humanity-style web game for friends. It uses one Next.js + React + TypeScript project, a custom Node.js server, Socket.IO, and in-memory rooms.

## Assumptions

- This is for private friend groups, so there is no authentication, moderation, database, account system, or public room directory.
- Nicknames are treated as seat keys. If a player disconnects, they can rejoin the same room with the same nickname and reclaim the same seat.
- Only connected non-judge players are required to submit before the judge sees answers.
- Placeholder cards are intentionally tame and local-only for now.
- Rooms are temporary. Restarting the Node.js server deletes every room.
- The first judge is chosen automatically when the host starts the game.

## Windows Setup

1. Install Node.js if needed from [nodejs.org](https://nodejs.org/). Use the current LTS version.
2. Open PowerShell in this folder:

   ```powershell
   cd "C:\Users\JonnoR\Documents\Codex\2026-05-28\AmazinResellerTycoon_Alpha1_Web\party-card-game"
   ```

3. Install dependencies:

   ```powershell
   npm install
   ```

4. Start the dev server:

   ```powershell
   npm run dev
   ```

5. Open:

   ```text
   http://localhost:3000
   ```

## Useful Scripts

```powershell
npm run dev
npm run typecheck
npm run build
npm run start
npm run cards:generate
npm run cards:dedupe
npm run cards:export
npm run decks:import
```

`npm run start` runs the same custom server in production mode after `npm run build`.

## Card Factory

The Card Factory is a developer-only card creation tool. It does not run during gameplay, does not call AI services, does not use paid APIs, and does not use a database. The live game still imports its current placeholder cards from `lib/cards.ts`.

Generate candidate cards:

```powershell
npm run cards:generate
```

This writes 100 prompt candidates and 500 answer candidates to:

```text
data/generated/candidate-cards.json
```

Clean duplicate candidate data:

```powershell
npm run cards:dedupe
```

This trims card text and removes duplicate text matches, case-insensitive text matches, and duplicate IDs.

Approve or reject cards manually by editing each candidate in `data/generated/candidate-cards.json`:

```json
{
  "status": "approved"
}
```

Valid statuses are `candidate`, `approved`, and `rejected`. Only `approved` cards are exported into the playable generated deck.

Export approved cards:

```powershell
npm run cards:export
```

This writes playable cards to:

```text
lib/generatedDeck.ts
```

The exported file uses the same `{ id, type, text }` card shape as the game. It is intentionally separate from `lib/cards.ts`, so exporting does not replace the current working placeholder deck unless a developer later changes the game import.

## Deck Importer

The deck importer is a development-time tool for pulling cards from the CrCast API and saving them locally. It does not modify gameplay, replace `lib/cards.ts`, or remove the placeholder decks.

Run the importer:

```powershell
npm run decks:import
```

It fetches these deck codes:

```text
SBYGD
HA7D0
R7XYE
Q5KQJ
BRJPQ
VJBB9
YYSDC
57QMS
35RXG
VNQPW
ZQW8G
PA8XH
BC3TS
L37HP
KW0IS
XLIZW
IDXPI
GCNYB
KXNLT
N4GCV
DIBZN
W8A2O
```

Deck codes live in one source of truth in `tools/deck-importer/importDecks.ts`. To add a deck, add its code to `CONFIGURED_DECK_CODES`. The importer trims, uppercases, and deduplicates that configured list before fetching. The report shows total configured deck codes, unique deck codes, and duplicate deck codes removed.

Raw API responses are stored here:

```text
data/imported/raw/
```

For example:

```text
data/imported/raw/SBYGD.json
```

Normalized cards are stored here:

```text
data/imported/normalized/cards.json
```

Import summary statistics are stored here:

```text
data/imported/normalized/deck-summary.json
```

The normalized card shape is:

```json
{
  "id": "SBYGD-p-0001",
  "sourceDeck": "SBYGD",
  "type": "prompt",
  "text": "Prompt text"
}
```

Image cards are detected for reporting, but excluded from the playable normalized deck because remote image links may be blocked, broken, or unavailable:

```json
{
  "id": "57QMS-a-0001",
  "sourceDeck": "57QMS",
  "type": "answer",
  "imageUrl": "https://i.imgur.com/example.jpg"
}
```

Inspect imported data with PowerShell:

```powershell
Get-Content data\imported\normalized\cards.json -Raw
Get-Content data\imported\normalized\deck-summary.json -Raw
Get-Content data\imported\raw\SBYGD.json -Raw
```

The importer prints a report with configured deck counts, unique deck counts, duplicate removal counts, per-deck prompt counts, text answer counts, excluded image card counts, excluded mixed card counts, and success or failure status. If one deck fails, the importer records the failure and continues with the remaining decks.

## Active Gameplay Deck

Gameplay loads cards from local files only. It never calls the CrCast API while a room is running.

At server startup, the game checks:

```text
data/imported/normalized/cards.json
```

If that file exists, is valid JSON, and contains at least 20 text prompt cards and 50 text answer cards, it becomes the active gameplay deck. Imported cards are converted into the existing in-game card shape:

```json
{
  "id": "SBYGD-p-0001",
  "type": "prompt",
  "text": "Prompt text"
}
```

If the imported file is missing, invalid, or too small, the game falls back to the placeholder cards in:

```text
lib/cards.ts
```

The server logs which text-only deck was selected at startup, including prompt and answer counts:

```text
[deck] Using imported deck. Prompts: 566. Text answers: 1664. Excluded image answers: 1483.
```

To refresh the imported deck, run:

```powershell
npm run decks:import
```

Then restart the dev server so the active deck is loaded again.

Image answer cards are not used in gameplay. They are imported and counted in `deck-summary.json`, then excluded from `cards.json` so classic gameplay stays text-only.

## How It Works

- `server.ts` starts Next.js and attaches a Socket.IO server to the same HTTP server.
- Rooms live in a `Map<string, Room>` in memory on the Node.js process.
- Creating a room generates a short 5-character room code and creates the host player.
- Joining a room adds a player while the room is in the lobby, or reconnects an existing disconnected seat if the nickname matches.
- Each socket joins a private Socket.IO room named after its player id, so the server can send each player a room view containing only their own hand.
- Public room updates hide submitted answer cards until all connected non-judge players have submitted.
- Revealed submissions use anonymous submission ids. The browser never receives the submitter for each answer; the server maps the winning submission back to the scoring player.
- Non-judge players are dealt back up to 10 answer cards at the start of each round after the previous winner is chosen.
- Game logic lives in `lib/gameLogic.ts`; active deck selection lives in `lib/activeDeck.ts`; shared TypeScript types live in `lib/types.ts`; placeholder cards live in `lib/cards.ts`.
- The development-time Card Factory lives in `tools/card-factory/cardFactory.ts`.
- The development-time CrCast deck importer lives in `tools/deck-importer/importDecks.ts`.

## Testing Multiplayer Locally

1. Run `npm run dev`.
2. Open `http://localhost:3000` in three different browser windows or tabs.
3. Create a room in the first window.
4. Join the same room code from the other windows with different nicknames.
5. Start the game from the host window.
6. Submit one answer from each non-judge window.
7. Use the judge window to pick an anonymous winning answer.
8. Confirm the score increments, hands refill, the judge rotates, and the next round starts automatically.

To test reconnects, close one window during the game, reopen `http://localhost:3000`, join with the same room code and nickname, and confirm the same seat, score, hand, and round state return.

## Current Limitations

- All state disappears when the server restarts.
- There is no authentication, so nickname reuse is trust-based.
- Rooms are not cleaned up automatically after everyone leaves.
- There is no deployment setup yet.
- There is no runtime card generation, custom cards, card packs, avatars, moderation, or accounts.
- A game in progress does not accept brand-new players.
- If the judge disconnects mid-round, the room currently waits for that judge to reconnect.
