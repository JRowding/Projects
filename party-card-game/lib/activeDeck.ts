import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { answerCards as placeholderAnswerCards, promptCards as placeholderPromptCards } from "./cards";
import type { Card, CardType } from "./types";

type ImportedCard = {
  id?: unknown;
  sourceDeck?: unknown;
  type?: unknown;
  text?: unknown;
  imageUrl?: unknown;
  cardFormat?: unknown;
};

type ImportedDeckSummary = {
  excludedImageCardCount?: unknown;
};

type DeckLoadResult = {
  source: "imported" | "placeholder";
  promptCards: Card[];
  answerCards: Card[];
  reason: string;
};

const IMPORTED_DECK_PATH = resolve("data/imported/normalized/cards.json");
const IMPORTED_DECK_SUMMARY_PATH = resolve("data/imported/normalized/deck-summary.json");
const MIN_IMPORTED_PROMPTS = 20;
const MIN_IMPORTED_ANSWERS = 50;

const activeDeck = loadActiveDeck();

export const promptCards = activeDeck.promptCards;
export const answerCards = activeDeck.answerCards;

function loadActiveDeck(): DeckLoadResult {
  try {
    const raw = readFileSync(IMPORTED_DECK_PATH, "utf8");
    const parsed = JSON.parse(raw) as unknown;

    if (!Array.isArray(parsed)) {
      return usePlaceholder("imported deck JSON is not an array");
    }

    const importedCards = parsed.flatMap(normalizeImportedCard);
    const importedPromptCards = importedCards.filter((card) => card.type === "prompt");
    const importedAnswerCards = importedCards.filter((card) => card.type === "answer");

    if (importedPromptCards.length < MIN_IMPORTED_PROMPTS) {
      return usePlaceholder(
        `imported deck has ${importedPromptCards.length} prompts; need at least ${MIN_IMPORTED_PROMPTS}`
      );
    }

    if (importedAnswerCards.length < MIN_IMPORTED_ANSWERS) {
      return usePlaceholder(
        `imported deck has ${importedAnswerCards.length} answers; need at least ${MIN_IMPORTED_ANSWERS}`
      );
    }

    logDeckChoice("imported", importedPromptCards, importedAnswerCards, undefined, readExcludedImageCount());
    return {
      source: "imported",
      promptCards: importedPromptCards,
      answerCards: importedAnswerCards,
      reason: "imported deck passed validation"
    };
  } catch (error) {
    const reason = error instanceof Error ? error.message : "unknown imported deck load error";
    return usePlaceholder(reason);
  }
}

function normalizeImportedCard(value: ImportedCard): Card[] {
  if (!isRecord(value)) {
    return [];
  }

  const type = normalizeType(value.type);
  const text = typeof value.text === "string" ? value.text.trim() : "";
  const hasImageUrl = typeof value.imageUrl === "string" && value.imageUrl.trim().length > 0;
  const cardFormat = value.cardFormat;
  const id = typeof value.id === "string" ? value.id.trim() : "";

  if (!type || !id) {
    return [];
  }

  if (type === "prompt" && !text) {
    return [];
  }

  if (type === "answer" && !text) {
    return [];
  }

  if (hasImageUrl || cardFormat === "image" || cardFormat === "mixed") {
    return [];
  }

  return [
    {
      id,
      type,
      text,
      cardFormat: "text"
    }
  ];
}

function normalizeType(value: unknown): CardType | null {
  if (value === "prompt" || value === "answer") {
    return value;
  }

  return null;
}

function usePlaceholder(reason: string): DeckLoadResult {
  const prompts = placeholderPromptCards.map(asTextCard);
  const answers = placeholderAnswerCards.map(asTextCard);
  logDeckChoice("placeholder", prompts, answers, reason, 0);
  return {
    source: "placeholder",
    promptCards: prompts,
    answerCards: answers,
    reason
  };
}

function asTextCard(card: Card): Card {
  return {
    ...card,
    cardFormat: "text"
  };
}

function logDeckChoice(
  source: DeckLoadResult["source"],
  prompts: Card[],
  answers: Card[],
  reason?: string,
  excludedImageAnswers = 0
) {
  const detail = reason ? ` (${reason})` : "";
  console.log(
    `[deck] Using ${source} deck${detail}. Prompts: ${prompts.length}. Text answers: ${answers.length}. Excluded image answers: ${excludedImageAnswers}.`
  );
}

function readExcludedImageCount() {
  try {
    const raw = readFileSync(IMPORTED_DECK_SUMMARY_PATH, "utf8");
    const parsed = JSON.parse(raw) as ImportedDeckSummary;
    return typeof parsed.excludedImageCardCount === "number" ? parsed.excludedImageCardCount : 0;
  } catch {
    return 0;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
