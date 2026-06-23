export type CardType = "prompt" | "answer";
export type CardFormat = "text" | "image" | "mixed";

export type Card = {
  id: string;
  type: CardType;
  text?: string;
  imageUrl?: string;
  cardFormat?: CardFormat;
};

export type Player = {
  id: string;
  nickname: string;
  seat: number;
  connected: boolean;
  isHost: boolean;
  score: number;
  hand: Card[];
};

export type Submission = {
  id: string;
  playerId: string;
  card: Card;
};

export type GamePhase = "lobby" | "playing" | "judging" | "gameOver";

export type GameState = {
  phase: GamePhase;
  targetScore: number;
  roundNumber: number;
  judgePlayerId: string | null;
  promptCard: Card | null;
  submissions: Submission[];
  winnerPlayerId: string | null;
  previousRoundWinnerPlayerId: string | null;
  previousRoundWinningCard: Card | null;
};

export type Room = {
  code: string;
  hostPlayerId: string;
  players: Player[];
  answerDeck: Card[];
  promptDeck: Card[];
  discardPile: Card[];
  game: GameState;
};

export type PublicPlayer = Omit<Player, "hand"> & {
  handCount: number;
};

export type PublicSubmission = {
  id: string;
  card: Card | null;
};

export type PublicRoom = {
  code: string;
  hostPlayerId: string;
  players: PublicPlayer[];
  meSubmittedThisRound: boolean;
  game: Omit<GameState, "submissions"> & {
    submissions: PublicSubmission[];
  };
  me: Player | null;
};

export type ClientToServerEvents = {
  createRoom: (
    payload: { nickname: string },
    callback: (result: SocketResult) => void
  ) => void;
  joinRoom: (
    payload: { code: string; nickname: string },
    callback: (result: SocketResult) => void
  ) => void;
  startGame: (payload: { code: string; playerId: string }) => void;
  submitAnswer: (
    payload: { code: string; playerId: string; cardId: string }
  ) => void;
  selectWinner: (
    payload: { code: string; playerId: string; submissionId: string }
  ) => void;
};

export type ServerToClientEvents = {
  roomUpdate: (room: PublicRoom) => void;
  roomError: (message: string) => void;
};

export type SocketResult =
  | { ok: true; code: string; playerId: string }
  | { ok: false; error: string };
