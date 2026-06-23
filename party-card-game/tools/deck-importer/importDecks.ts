import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

type ImportedCardType = "prompt" | "answer";
type CardFormat = "text" | "image" | "mixed";

type NormalizedCard = {
  id: string;
  sourceDeck: string;
  type: ImportedCardType;
  text: string;
};

type DeckReport = {
  code: string;
  success: boolean;
  textPromptCount: number;
  textAnswerCount: number;
  excludedImageCardCount: number;
  excludedMixedCardCount: number;
  excludedCardCount: number;
  error?: string;
};

type DeckSummary = {
  generatedAt: string;
  totalConfiguredDeckCodes: number;
  uniqueDeckCodes: number;
  duplicateDeckCodesRemoved: number;
  uniqueDecksImported: number;
  successfulImports: number;
  failedImports: number;
  promptCardCount: number;
  textAnswerCount: number;
  excludedImageCardCount: number;
  excludedMixedCardCount: number;
  excludedCardCount: number;
  decks: DeckReport[];
};

const CONFIGURED_DECK_CODES = [
  "SBYGD",
  "HA7D0",
  "R7XYE",
  "Q5KQJ",
  "BRJPQ",
  "VJBB9",
  "YYSDC",
  "57QMS",
  "35RXG",
  "VNQPW",
  "ZQW8G",
  "PA8XH",
  "BC3TS",
  "L37HP",
  "KW0IS",
  "XLIZW",
  "IDXPI",
  "GCNYB",
  "KXNLT",
  "N4GCV",
  "DIBZN",
  "W8A2O"
];
const UNIQUE_DECK_CODES = dedupeDeckCodes(CONFIGURED_DECK_CODES);
const API_BASE = "https://api.crcast.cc/v1/cc/decks";
const RAW_DIR = resolve("data/imported/raw");
const NORMALIZED_PATH = resolve("data/imported/normalized/cards.json");
const SUMMARY_PATH = resolve("data/imported/normalized/deck-summary.json");

async function main() {
  const allCards: NormalizedCard[] = [];
  const reports: DeckReport[] = [];

  for (const code of UNIQUE_DECK_CODES) {
    const report = await importDeck(code);
    reports.push(report.report);
    allCards.push(...report.cards);
  }

  await writeJson(NORMALIZED_PATH, allCards);
  await writeJson(SUMMARY_PATH, buildSummary(reports));
  printReport(reports);
}

async function importDeck(code: string): Promise<{ report: DeckReport; cards: NormalizedCard[] }> {
  const url = `${API_BASE}/${code}/cards/`;

  try {
    const response = await fetch(url, {
      headers: {
        accept: "application/json"
      }
    });
    const rawText = await response.text();
    const raw = parseRaw(rawText);

    await writeRaw(resolve(RAW_DIR, `${code}.json`), rawText);

    if (!response.ok) {
      return {
        cards: [],
        report: {
          code,
          success: false,
          textPromptCount: 0,
          textAnswerCount: 0,
          excludedImageCardCount: 0,
          excludedMixedCardCount: 0,
          excludedCardCount: 0,
          error: `HTTP ${response.status} ${response.statusText}`
        }
      };
    }

    const normalized = normalizeDeck(code, raw);
    return {
      cards: normalized.cards,
      report: {
        code,
        success: true,
        textPromptCount: normalized.cards.filter((card) => card.type === "prompt").length,
        textAnswerCount: normalized.cards.filter((card) => card.type === "answer").length,
        excludedImageCardCount: normalized.excludedImageCardCount,
        excludedMixedCardCount: normalized.excludedMixedCardCount,
        excludedCardCount: normalized.excludedImageCardCount + normalized.excludedMixedCardCount
      }
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await writeJson(resolve(RAW_DIR, `${code}.json`), {
      ok: false,
      url,
      error: message
    });

    return {
      cards: [],
      report: {
        code,
        success: false,
        textPromptCount: 0,
        textAnswerCount: 0,
        excludedImageCardCount: 0,
        excludedMixedCardCount: 0,
        excludedCardCount: 0,
        error: message
      }
    };
  }
}

function normalizeDeck(code: string, raw: unknown): {
  cards: NormalizedCard[];
  excludedImageCardCount: number;
  excludedMixedCardCount: number;
} {
  const cards: NormalizedCard[] = [];
  let excludedImageCardCount = 0;
  let excludedMixedCardCount = 0;

  for (const entry of extractEntries(raw)) {
    const content = contentFromUnknown(entry.value);
    if (!content.text && !content.imageUrl) {
      continue;
    }

    const cardFormat = getCardFormat(content);
    if (cardFormat === "image") {
      excludedImageCardCount += 1;
      continue;
    }

    if (cardFormat === "mixed") {
      excludedMixedCardCount += 1;
      continue;
    }

    if (!content.text || containsOnlyImageMarkup(content.text)) {
      excludedImageCardCount += 1;
      continue;
    }

    cards.push({
      id: makeCardId(code, entry.type, entry.value, cards.length),
      sourceDeck: code,
      type: entry.type,
      text: content.text
    });
  }

  return {
    cards: dedupeNormalized(cards),
    excludedImageCardCount,
    excludedMixedCardCount
  };
}

function extractEntries(raw: unknown): Array<{ type: ImportedCardType; value: unknown }> {
  if (Array.isArray(raw)) {
    return raw.flatMap((value) => {
      const type = typeFromUnknown(value);
      return type ? [{ type, value }] : [];
    });
  }

  if (!isRecord(raw)) {
    return [];
  }

  const entries: Array<{ type: ImportedCardType; value: unknown }> = [];
  entries.push(...entriesFromNamedArray(raw, "calls", "prompt"));
  entries.push(...entriesFromNamedArray(raw, "prompts", "prompt"));
  entries.push(...entriesFromNamedArray(raw, "black", "prompt"));
  entries.push(...entriesFromNamedArray(raw, "questions", "prompt"));
  entries.push(...entriesFromNamedArray(raw, "responses", "answer"));
  entries.push(...entriesFromNamedArray(raw, "answers", "answer"));
  entries.push(...entriesFromNamedArray(raw, "white", "answer"));

  if (Array.isArray(raw.cards)) {
    entries.push(
      ...raw.cards.flatMap((value) => {
        const type = typeFromUnknown(value);
        return type ? [{ type, value }] : [];
      })
    );
  }

  if (raw.data) {
    entries.push(...extractEntries(raw.data));
  }

  return entries;
}

function entriesFromNamedArray(
  raw: Record<string, unknown>,
  key: string,
  type: ImportedCardType
) {
  const value = raw[key];
  return Array.isArray(value) ? value.map((card) => ({ type, value: card })) : [];
}

function typeFromUnknown(value: unknown): ImportedCardType | null {
  if (!isRecord(value)) {
    return null;
  }

  const rawType = String(
    value.type ?? value.cardType ?? value.card_type ?? value.kind ?? value.category ?? ""
  ).toLocaleLowerCase();

  if (["prompt", "black", "call", "question"].includes(rawType)) {
    return "prompt";
  }

  if (["answer", "white", "response"].includes(rawType)) {
    return "answer";
  }

  if ("call" in value || "prompt" in value || "question" in value) {
    return "prompt";
  }

  if ("response" in value || "answer" in value) {
    return "answer";
  }

  return null;
}

function contentFromUnknown(value: unknown): { text?: string; imageUrl?: string } {
  if (typeof value === "string") {
    return parseContentText(value);
  }

  if (Array.isArray(value)) {
    return mergeContent(value.map(contentFromUnknown));
  }

  if (!isRecord(value)) {
    return {};
  }

  const possibleText =
    value.text ??
    value.content ??
    value.card ??
    value.call ??
    value.prompt ??
    value.question ??
    value.response ??
    value.answer;

  if (possibleText !== undefined) {
    return contentFromUnknown(possibleText);
  }

  if (Array.isArray(value.parts)) {
    return contentFromUnknown(value.parts);
  }

  return {};
}

function parseContentText(value: string): { text?: string; imageUrl?: string } {
  const imageMatches = [...value.matchAll(/\[img\](https?:\/\/[^\]]+)\[\/img\]/gi)];
  const imageUrl = imageMatches[0]?.[1]?.trim();
  const text = cleanText(value.replace(/\[img\]https?:\/\/[^\]]+\[\/img\]/gi, ""));

  return {
    ...(text ? { text } : {}),
    ...(imageUrl ? { imageUrl } : {})
  };
}

function mergeContent(parts: Array<{ text?: string; imageUrl?: string }>) {
  const text = cleanText(parts.map((part) => part.text).filter(Boolean).join(" ____ "));
  const imageUrl = parts.find((part) => part.imageUrl)?.imageUrl;

  return {
    ...(text ? { text } : {}),
    ...(imageUrl ? { imageUrl } : {})
  };
}

function getCardFormat(content: { text?: string; imageUrl?: string }): CardFormat {
  if (content.text && content.imageUrl) {
    return "mixed";
  }

  if (content.imageUrl) {
    return "image";
  }

  return "text";
}

function cleanText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function containsOnlyImageMarkup(value: string) {
  return /^\[img\]https?:\/\/[^\]]+\[\/img\]$/i.test(value.trim());
}

function makeCardId(
  deckCode: string,
  type: ImportedCardType,
  value: unknown,
  fallbackIndex: number
) {
  const rawId = isRecord(value) ? value.id ?? value.cardId ?? value.card_id : null;
  const suffix = rawId ? String(rawId) : String(fallbackIndex + 1).padStart(4, "0");
  return `${deckCode}-${type === "prompt" ? "p" : "a"}-${slug(suffix)}`;
}

function slug(value: string) {
  return value.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "card";
}

function dedupeNormalized(cards: NormalizedCard[]) {
  const seenIds = new Set<string>();
  const deduped: NormalizedCard[] = [];

  for (const card of cards) {
    if (seenIds.has(card.id)) {
      continue;
    }

    seenIds.add(card.id);
    deduped.push(card);
  }

  return deduped;
}

function dedupeDeckCodes(codes: string[]) {
  return Array.from(new Set(codes.map((code) => code.trim().toLocaleUpperCase()).filter(Boolean)));
}

function parseRaw(rawText: string) {
  try {
    return JSON.parse(rawText) as unknown;
  } catch {
    return rawText;
  }
}

function printReport(reports: DeckReport[]) {
  const summary = buildSummary(reports);

  console.log("");
  console.log("Deck import report");
  console.log("==================");
  console.log(`Total configured deck codes: ${summary.totalConfiguredDeckCodes}`);
  console.log(`Unique deck codes: ${summary.uniqueDeckCodes}`);
  console.log(`Duplicate deck codes removed: ${summary.duplicateDeckCodesRemoved}`);
  console.log(`Unique decks imported: ${summary.uniqueDecksImported}`);
  console.log(`Successful imports: ${summary.successfulImports}`);
  console.log(`Failed imports: ${summary.failedImports}`);
  console.log(`Prompt cards: ${summary.promptCardCount}`);
  console.log(`Text answer cards: ${summary.textAnswerCount}`);
  console.log(`Excluded image cards: ${summary.excludedImageCardCount}`);
  console.log(`Excluded mixed cards: ${summary.excludedMixedCardCount}`);
  console.log("");
  console.log("Deck   Prompts  Text answers  Excluded  Excl images  Excl mixed  Status");
  console.log("-----  -------  ------------  --------  -----------  ----------  ------");

  for (const report of reports) {
    const status = report.success ? "success" : `failed: ${report.error}`;
    console.log(
      `${report.code.padEnd(5)}  ${String(report.textPromptCount).padStart(7)}  ${String(
        report.textAnswerCount
      ).padStart(12)}  ${String(report.excludedCardCount).padStart(8)}  ${String(
        report.excludedImageCardCount
      ).padStart(11)}  ${String(
        report.excludedMixedCardCount
      ).padStart(10)}  ${status}`
    );
  }
}

function buildSummary(reports: DeckReport[]): DeckSummary {
  const successfulImports = reports.filter((report) => report.success).length;

  return {
    generatedAt: new Date().toISOString(),
    totalConfiguredDeckCodes: CONFIGURED_DECK_CODES.length,
    uniqueDeckCodes: UNIQUE_DECK_CODES.length,
    duplicateDeckCodesRemoved: CONFIGURED_DECK_CODES.length - UNIQUE_DECK_CODES.length,
    uniqueDecksImported: reports.length,
    successfulImports,
    failedImports: reports.length - successfulImports,
    promptCardCount: reports.reduce((total, report) => total + report.textPromptCount, 0),
    textAnswerCount: reports.reduce((total, report) => total + report.textAnswerCount, 0),
    excludedImageCardCount: reports.reduce(
      (total, report) => total + report.excludedImageCardCount,
      0
    ),
    excludedMixedCardCount: reports.reduce(
      (total, report) => total + report.excludedMixedCardCount,
      0
    ),
    excludedCardCount: reports.reduce((total, report) => total + report.excludedCardCount, 0),
    decks: reports
  };
}

async function writeJson(path: string, data: unknown) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

async function writeRaw(path: string, data: string) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, data, "utf8");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
