import { createServer } from "node:http";
import next from "next";
import { Server } from "socket.io";
import {
  createRoom,
  generateRoomCode,
  joinOrReconnect,
  markDisconnected,
  selectWinner,
  startGame,
  submitAnswer,
  toPublicRoom,
  normaliseNickname
} from "./lib/gameLogic";
import type {
  ClientToServerEvents,
  Room,
  ServerToClientEvents,
  SocketResult
} from "./lib/types";

const port = Number(process.env.PORT ?? 3000);
const dev = process.argv.includes("--prod") ? false : process.env.NODE_ENV !== "production";
const app = next({ dev });
const handle = app.getRequestHandler();
const rooms = new Map<string, Room>();
const socketPlayers = new Map<string, { code: string; playerId: string }>();
const playerSockets = new Map<string, Set<string>>();

function emitRoom(io: Server<ClientToServerEvents, ServerToClientEvents>, room: Room) {
  for (const player of room.players) {
    io.to(player.id).emit("roomUpdate", toPublicRoom(room, player.id));
  }
}

function emitRoomError(
  io: Server<ClientToServerEvents, ServerToClientEvents>,
  room: Room,
  message: string
) {
  for (const player of room.players) {
    io.to(player.id).emit("roomError", message);
  }
}

function fail(callback: (result: SocketResult) => void, error: string) {
  callback({ ok: false, error });
}

app.prepare().then(() => {
  const httpServer = createServer((req, res) => {
    handle(req, res);
  });

  const io = new Server<ClientToServerEvents, ServerToClientEvents>(httpServer);

  io.on("connection", (socket) => {
    socket.on("createRoom", ({ nickname }, callback) => {
      try {
        const cleaned = normaliseNickname(nickname);
        if (!cleaned) {
          fail(callback, "Enter a nickname.");
          return;
        }

        const code = generateRoomCode(new Set(rooms.keys()));
        const room = createRoom(code, cleaned);
        const player = room.players[0];

        rooms.set(code, room);
        socket.join(player.id);
        socketPlayers.set(socket.id, { code, playerId: player.id });
        registerPlayerSocket(player.id, socket.id);
        callback({ ok: true, code, playerId: player.id });
        emitRoom(io, room);
      } catch (error) {
        fail(callback, error instanceof Error ? error.message : "Could not create room.");
      }
    });

    socket.on("joinRoom", ({ code, nickname }, callback) => {
      try {
        const cleanedCode = code.trim().toLocaleUpperCase();
        const room = rooms.get(cleanedCode);
        const cleanedNickname = normaliseNickname(nickname);

        if (!cleanedNickname) {
          fail(callback, "Enter a nickname.");
          return;
        }

        if (!room) {
          fail(callback, "Room not found.");
          return;
        }

        const player = joinOrReconnect(room, cleanedNickname);
        socket.join(player.id);
        socketPlayers.set(socket.id, { code: cleanedCode, playerId: player.id });
        registerPlayerSocket(player.id, socket.id);
        callback({ ok: true, code: cleanedCode, playerId: player.id });
        emitRoom(io, room);
      } catch (error) {
        fail(callback, error instanceof Error ? error.message : "Could not join room.");
      }
    });

    socket.on("startGame", ({ code, playerId }) => {
      runRoomAction(io, code, (room) => startGame(room, playerId));
    });

    socket.on("submitAnswer", ({ code, playerId, cardId }) => {
      runRoomAction(io, code, (room) => submitAnswer(room, playerId, cardId));
    });

    socket.on("selectWinner", ({ code, playerId, submissionId }) => {
      runRoomAction(io, code, (room) => selectWinner(room, playerId, submissionId));
    });

    socket.on("disconnect", () => {
      const session = socketPlayers.get(socket.id);
      if (!session) {
        return;
      }

      const room = rooms.get(session.code);
      socketPlayers.delete(socket.id);
      unregisterPlayerSocket(session.playerId, socket.id);

      if (room && !hasLivePlayerSocket(session.playerId)) {
        markDisconnected(room, session.playerId);
        emitRoom(io, room);
      }
    });
  });

  httpServer.listen(port, () => {
    console.log(`Ready on http://localhost:${port}`);
  });
});

function runRoomAction(
  io: Server<ClientToServerEvents, ServerToClientEvents>,
  code: string,
  action: (room: Room) => void
) {
  const room = rooms.get(code.trim().toLocaleUpperCase());

  if (!room) {
    return;
  }

  try {
    action(room);
    emitRoom(io, room);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Action failed.";
    emitRoomError(io, room, message);
  }
}

function registerPlayerSocket(playerId: string, socketId: string) {
  const sockets = playerSockets.get(playerId) ?? new Set<string>();
  sockets.add(socketId);
  playerSockets.set(playerId, sockets);
}

function unregisterPlayerSocket(playerId: string, socketId: string) {
  const sockets = playerSockets.get(playerId);
  if (!sockets) {
    return;
  }

  sockets.delete(socketId);
  if (sockets.size === 0) {
    playerSockets.delete(playerId);
  }
}

function hasLivePlayerSocket(playerId: string) {
  return (playerSockets.get(playerId)?.size ?? 0) > 0;
}
