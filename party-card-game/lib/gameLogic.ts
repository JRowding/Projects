import { answerCards, promptCards } from "./activeDeck";
import { randomUUID } from "node:crypto";
import type { Card, Player, PublicRoom, Room, Submission } from "./types";

const ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const MAX_PLAYERS = 8;
const MIN_PLAYERS = 3;
const HAND_SIZE = 10;
const DEFAULT_TARGET_SCORE = 5;

export function normaliseNickname(nickname: string) {
  return nickname.trim().replace(/\s+/g, " ").slice(0, 24);
}

export function generateRoomCode(existingCodes: Set<string>) {
  let code = "";

  do {
    code = Array.from({ length: 5 }, () =>
      ROOM_CODE_ALPHABET[Math.floor(Math.random() * ROOM_CODE_ALPHABET.length)]
    ).join("");
  } while (existingCodes.has(code));

  return code;
}

export function createRoom(code: string, hostNickname: string): Room {
  const host = createPlayer(hostNickname, 1, true);
  const answerDeck = shuffle([...answerCards]);
  const promptDeck = shuffle([...promptCards]);

  return {
    code,
    hostPlayerId: host.id,
    players: [host],
    answerDeck,
    promptDeck,
    discardPile: [],
    game: {
      phase: "lobby",
      targetScore: DEFAULT_TARGET_SCORE,
      roundNumber: 0,
      judgePlayerId: null,
      promptCard: null,
      submissions: [],
      winnerPlayerId: null,
      previousRoundWinnerPlayerId: null,
      previousRoundWinningCard: null
    }
  };
}

export function joinOrReconnect(room: Room, nickname: string): Player {
  const cleaned = normaliseNickname(nickname);
  const existing = findPlayerByNickname(room, cleaned);

  if (existing) {
    existing.connected = true;
    if (room.game.phase === "playing" && existing.id !== room.game.judgePlayerId) {
      drawToHand(existing, room);
    }
    return existing;
  }

  if (room.players.length >= MAX_PLAYERS) {
    throw new Error("This room is full.");
  }

  if (room.game.phase !== "lobby") {
    throw new Error("This game has already started.");
  }

  const player = createPlayer(cleaned, room.players.length + 1, false);
  room.players.push(player);
  return player;
}

export function markDisconnected(room: Room, playerId: string) {
  const player = room.players.find((candidate) => candidate.id === playerId);
  if (player) {
    player.connected = false;
  }

  revealIfRoundReady(room);
}

export function startGame(room: Room, playerId: string) {
  assertPhase(room, "lobby");

  if (room.hostPlayerId !== playerId) {
    throw new Error("Only the host can start the game.");
  }

  const connectedPlayers = getConnectedPlayers(room);
  if (connectedPlayers.length < MIN_PLAYERS) {
    throw new Error("You need at least 3 connected players to start.");
  }

  if (connectedPlayers.length > MAX_PLAYERS) {
    throw new Error("This game supports up to 8 players.");
  }

  room.players.forEach((player) => {
    player.score = 0;
    player.hand = [];
  });

  beginRound(room);
}

export function submitAnswer(room: Room, playerId: string, cardId: string) {
  assertPhase(room, "playing");

  if (room.game.judgePlayerId === playerId) {
    throw new Error("The judge cannot submit an answer.");
  }

  if (!isActivePlayer(room, playerId)) {
    throw new Error("Only connected players can submit.");
  }

  if (room.game.submissions.some((submission) => submission.playerId === playerId)) {
    throw new Error("You have already submitted this round.");
  }

  const player = getPlayer(room, playerId);
  const cardIndex = player.hand.findIndex((card) => card.id === cardId);

  if (cardIndex === -1) {
    throw new Error("That card is not in your hand.");
  }

  const [card] = player.hand.splice(cardIndex, 1);
  room.game.submissions.push({ id: randomUUID(), playerId, card });

  revealIfRoundReady(room);
}

export function selectWinner(room: Room, judgePlayerId: string, submissionId: string) {
  assertPhase(room, "judging");

  if (room.game.judgePlayerId !== judgePlayerId) {
    throw new Error("Only the judge can pick a winner.");
  }

  const winningSubmission = room.game.submissions.find(
    (submission) => submission.id === submissionId
  );

  if (!winningSubmission) {
    throw new Error("That submission is not available this round.");
  }

  if (room.game.winnerPlayerId) {
    throw new Error("A winner has already been selected for this round.");
  }

  const winner = getPlayer(room, winningSubmission.playerId);
  winner.score += 1;
  room.discardPile.push(...room.game.submissions.map((submission) => submission.card));
  room.game.winnerPlayerId = winner.id;
  room.game.previousRoundWinnerPlayerId = winner.id;
  room.game.previousRoundWinningCard = winningSubmission.card;

  room.players.forEach((player) => {
    if (player.id !== room.game.judgePlayerId) {
      drawToHand(player, room);
    }
  });

  if (winner.score >= room.game.targetScore) {
    room.game.phase = "gameOver";
    return;
  }

  beginRound(room);
}

export function toPublicRoom(room: Room, viewerPlayerId: string | null): PublicRoom {
  const viewer = viewerPlayerId
    ? room.players.find((player) => player.id === viewerPlayerId) ?? null
    : null;
  const revealSubmissions = room.game.phase === "judging" || room.game.phase === "gameOver";

  return {
    code: room.code,
    hostPlayerId: room.hostPlayerId,
    meSubmittedThisRound: Boolean(
      viewerPlayerId &&
        room.game.submissions.some((submission) => submission.playerId === viewerPlayerId)
    ),
    players: room.players.map((player) => ({
      id: player.id,
      nickname: player.nickname,
      seat: player.seat,
      connected: player.connected,
      isHost: player.isHost,
      score: player.score,
      handCount: player.hand.length
    })),
    game: {
      ...room.game,
      submissions: room.game.submissions.map((submission, index) =>
        revealSubmissions
          ? {
              id: submission.id,
              card: submission.card
            }
          : {
              id: `hidden-${index}`,
              card: null
            }
      )
    },
    me: viewer ? { ...viewer, hand: [...viewer.hand] } : null
  };
}

function beginRound(room: Room) {
  const connectedPlayers = getConnectedPlayers(room);
  const previousJudgeId = room.game.judgePlayerId;
  const previousJudgeIndex = previousJudgeId
    ? connectedPlayers.findIndex((player) => player.id === previousJudgeId)
    : -1;
  const judge = connectedPlayers[(previousJudgeIndex + 1) % connectedPlayers.length];

  room.game.phase = "playing";
  room.game.roundNumber += 1;
  room.game.judgePlayerId = judge.id;
  room.game.promptCard = drawPrompt(room);
  room.game.submissions = [];
  room.game.winnerPlayerId = null;

  connectedPlayers
    .filter((player) => player.id !== judge.id)
    .forEach((player) => drawToHand(player, room));
}

function createPlayer(nickname: string, seat: number, isHost: boolean): Player {
  return {
    id: randomUUID(),
    nickname,
    seat,
    connected: true,
    isHost,
    score: 0,
    hand: []
  };
}

function drawToHand(player: Player, room: Room) {
  const existingCardIds = new Set(player.hand.map((card) => card.id));
  let attempts = 0;

  while (player.hand.length < HAND_SIZE && attempts < answerCards.length * 2) {
    attempts += 1;

    if (room.answerDeck.length === 0) {
      room.answerDeck = shuffle(room.discardPile.splice(0));
    }

    const card = room.answerDeck.pop();
    if (card) {
      if (!existingCardIds.has(card.id)) {
        player.hand.push(card);
        existingCardIds.add(card.id);
      } else {
        room.discardPile.unshift(card);
      }
    } else {
      break;
    }
  }
}

function drawPrompt(room: Room) {
  if (room.promptDeck.length === 0) {
    room.promptDeck = shuffle([...promptCards]);
  }

  const prompt = room.promptDeck.pop();
  if (!prompt) {
    throw new Error("No prompt cards are available.");
  }

  return prompt;
}

function findPlayerByNickname(room: Room, nickname: string) {
  const target = nickname.toLocaleLowerCase();
  return room.players.find((player) => player.nickname.toLocaleLowerCase() === target);
}

function getPlayer(room: Room, playerId: string): Player {
  const player = room.players.find((candidate) => candidate.id === playerId);
  if (!player) {
    throw new Error("Player not found.");
  }

  return player;
}

function getConnectedPlayers(room: Room) {
  return room.players.filter((player) => player.connected);
}

function isActivePlayer(room: Room, playerId: string) {
  return room.players.some((player) => player.id === playerId && player.connected);
}

function allActiveNonJudgesSubmitted(room: Room) {
  const submitted = new Set(
    room.game.submissions.map((submission: Submission) => submission.playerId)
  );

  return getConnectedPlayers(room)
    .filter((player) => player.id !== room.game.judgePlayerId)
    .every((player) => submitted.has(player.id));
}

function revealIfRoundReady(room: Room) {
  if (room.game.phase === "playing" && allActiveNonJudgesSubmitted(room)) {
    room.game.phase = "judging";
  }
}

function assertPhase(room: Room, expected: Room["game"]["phase"]) {
  if (room.game.phase !== expected) {
    throw new Error(`This action is not available while the game is ${room.game.phase}.`);
  }
}

function shuffle<T>(items: T[]) {
  for (let index = items.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
  }

  return items;
}
