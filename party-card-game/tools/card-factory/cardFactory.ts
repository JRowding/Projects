import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Card, CardType } from "../../lib/types";

type CandidateStatus = "candidate" | "approved" | "rejected";

type StyleCategory =
  | "pub-chaos"
  | "political-farce"
  | "reality-tv-meltdown"
  | "workplace-dread"
  | "nightlife-regret"
  | "football-nonsense"
  | "local-facebook-drama"
  | "family-awkwardness"
  | "gross-out"
  | "absurd-dark-comedy"
  | "tabloid-trash";

type CandidateCard = {
  id: string;
  type: CardType;
  text: string;
  tags: string[];
  intensity: 1 | 2 | 3 | 4 | 5;
  styleCategory: StyleCategory;
  createdAt: string;
  status: CandidateStatus;
  reviewNotes: string[];
};

type WordBank = {
  tag: string;
  styleCategory: StyleCategory;
  intensity: 1 | 2 | 3 | 4 | 5;
  subjects: string[];
  places: string[];
  objects: string[];
  actions: string[];
};

const CANDIDATE_PATH = resolve("data/generated/candidate-cards.json");
const EXPORT_PATH = resolve("lib/generatedDeck.ts");
const CREATED_AT = new Date().toISOString();

const wordBanks: WordBank[] = [
  {
    tag: "pubs",
    styleCategory: "pub-chaos",
    intensity: 3,
    subjects: ["the pub landlord", "a quiz team with no answers", "a man guarding the fruit machine"],
    places: ["a sticky Wetherspoons table", "the smoking area", "the pub toilet corridor"],
    objects: ["a flat pint", "a suspicious pork scratching", "the cursed karaoke mic"],
    actions: ["declaring themselves darts captain", "starting beef over crisps", "crying into the jukebox"]
  },
  {
    tag: "politics",
    styleCategory: "political-farce",
    intensity: 4,
    subjects: ["a backbench MP with lager breath", "a council candidate with haunted eyes", "a minister dodging the obvious question"],
    places: ["a village hall hustings", "a televised apology sofa", "the queue outside a polling station"],
    objects: ["a manifesto written on a napkin", "an expenses form full of nonsense", "a patriotic novelty mug"],
    actions: ["promising to fix bins with vibes", "resigning into a hedge", "calling it a robust process"]
  },
  {
    tag: "reality TV",
    styleCategory: "reality-tv-meltdown",
    intensity: 4,
    subjects: ["a Love Island reject with a podcast", "a reality TV villain in white jeans", "a crying contestant named Brad"],
    places: ["the reunion episode sofa", "a hot tub full of bad decisions", "the sponsored villa kitchen"],
    objects: ["a fake tan emergency kit", "a ring light of judgment", "a protein shaker full of secrets"],
    actions: ["weaponising the word loyal", "storming off for brand synergy", "confessing everything to camera three"]
  },
  {
    tag: "British workplaces",
    styleCategory: "workplace-dread",
    intensity: 3,
    subjects: ["the HR business partner", "a manager who says touch base", "the intern who knows too much"],
    places: ["a windowless meeting room", "the office kitchen crime scene", "a Teams call nobody wanted"],
    objects: ["a passive-aggressive mug", "a printer full of despair", "a spreadsheet named FINAL_FINAL_REAL"],
    actions: ["booking a meeting about morale", "replying all with menace", "circling back until everyone gives up"]
  },
  {
    tag: "nightlife",
    styleCategory: "nightlife-regret",
    intensity: 4,
    subjects: ["a hen do with matching sashes", "a bouncer who has seen everything", "a DJ allergic to requests"],
    places: ["the kebab shop at 2:17am", "a nightclub toilet mirror", "the last train home"],
    objects: ["a sticky Jagerbomb tray", "a shoe full of regret", "a taxi receipt with emotional damage"],
    actions: ["texting an ex with confidence", "losing the cloakroom ticket", "starting a dance circle nobody asked for"]
  },
  {
    tag: "football culture",
    styleCategory: "football-nonsense",
    intensity: 3,
    subjects: ["a Sunday league goalkeeper", "a bloke in a vintage away shirt", "the loudest man in the pub"],
    places: ["a freezing five-a-side pitch", "the away end queue", "a pub showing the early kickoff"],
    objects: ["a pie hotter than the sun", "a scarf with questionable spelling", "a VAR decision made by vibes"],
    actions: ["calling everyone ref", "explaining xG to a stranger", "two-footing a conversation"]
  },
  {
    tag: "local Facebook groups",
    styleCategory: "local-facebook-drama",
    intensity: 3,
    subjects: ["a neighbourhood watch admin", "a furious woman called Bev", "someone selling half a trampoline"],
    places: ["the local Facebook comments", "a driveway with three cones", "the community centre noticeboard"],
    objects: ["a blurry photo of a fox", "a lost parcel accusation", "a passive-aggressive bin post"],
    actions: ["asking if anyone heard that bang", "naming and shaming a wheelie bin", "declaring the high street finished"]
  },
  {
    tag: "awkward family events",
    styleCategory: "family-awkwardness",
    intensity: 3,
    subjects: ["a divorced uncle with opinions", "Nan after two sherries", "a cousin with a crypto pitch"],
    places: ["Boxing Day lunch", "a wedding table plan disaster", "the buffet beside the radiator"],
    objects: ["a suspicious trifle", "a family secret in a Tesco bag", "a birthday card with the wrong age"],
    actions: ["bringing up inheritance at pudding", "clapping on the wrong beat", "asking why you're still single"]
  },
  {
    tag: "gross-out humour",
    styleCategory: "gross-out",
    intensity: 5,
    subjects: ["a hungover flatmate", "the office fridge", "a festival toilet survivor"],
    places: ["a portaloo in July", "the back seat of a night bus", "a student kitchen sink"],
    objects: ["a damp sock with a backstory", "a bin juice cocktail", "a mystery stain with confidence"],
    actions: ["sniffing it and making things worse", "leaking through the carrier bag", "fermenting under the radiator"]
  },
  {
    tag: "absurd dark comedy",
    styleCategory: "absurd-dark-comedy",
    intensity: 5,
    subjects: ["a cursed ventriloquist dummy", "the concept of hope in a hi-vis vest", "a haunted meal deal"],
    places: ["a motorway services at midnight", "an abandoned soft play", "a budget funeral buffet with no context"],
    objects: ["a cursed urn full of loose change", "a raffle prize nobody survives socially", "a legal waiver made of ham"],
    actions: ["making eye contact with the void", "summoning Ofsted by accident", "whispering tax advice from a cupboard"]
  },
  {
    tag: "celebrity/tabloid references",
    styleCategory: "tabloid-trash",
    intensity: 4,
    subjects: ["a disgraced daytime TV guest", "a tabloid astrologer with receipts", "a celebrity chef's angry cousin"],
    places: ["a red-top splash page", "the back door of an awards afterparty", "a podcast apology tour"],
    objects: ["a super-injunction made of glitter", "a leaked voice note", "a fake tan scandal dossier"],
    actions: ["selling the story for petrol money", "crying exclusively to the tabloids", "launching a wellness brand by Monday"]
  }
];

const promptTemplates = [
  "The worst thing to hear in {place} is \"____\".",
  "{subject} ruined the evening by introducing ____.",
  "The real reason everyone left {place} was ____.",
  "The group chat exploded after {subject} posted ____.",
  "Nothing says modern Britain like ____ at {place}.",
  "The committee rejected the proposal after discovering ____.",
  "The emergency announcement at {place} was just ____.",
  "{subject} tried to explain ____ and somehow made it worse.",
  "The final straw was ____.",
  "The theme for tonight is ____."
];

const answerTemplates = [
  "{object}.",
  "{subject} {action}.",
  "{object} discovered behind {place}.",
  "A tactical deployment of {object}.",
  "Blaming everything on {subject}.",
  "Turning {place} into a crime scene with {object}.",
  "A legally troubling amount of {object}.",
  "{subject} loudly defending {object}.",
  "The emotional aftermath of {place}.",
  "{action} while everyone pretends not to notice."
];

const blockedPatterns = [
  /\b(child|children|minor|schoolgirl|schoolboy)\b/i,
  /\b(genocide|lynching|terrorist attack|mass shooting|murder victim)\b/i,
  /\bslur\b/i
];

async function main() {
  const command = process.argv[2];

  if (command === "generate") {
    await generate();
    return;
  }

  if (command === "dedupe") {
    await dedupe();
    return;
  }

  if (command === "export") {
    await exportApproved();
    return;
  }

  throw new Error("Use one of: generate, dedupe, export");
}

async function generate() {
  const cards = [
    ...buildCandidates("prompt", 100),
    ...buildCandidates("answer", 500)
  ];

  await writeJson(CANDIDATE_PATH, cards);
  console.log(`Generated ${cards.length} candidate cards at ${CANDIDATE_PATH}`);
}

async function dedupe() {
  const cards = await readCandidates();
  const deduped: CandidateCard[] = [];
  const seenIds = new Set<string>();
  const seenTexts = new Set<string>();

  for (const card of cards) {
    const normalizedText = card.text.trim().replace(/\s+/g, " ");
    const textKey = normalizedText.toLocaleLowerCase();

    if (seenIds.has(card.id) || seenTexts.has(textKey)) {
      continue;
    }

    seenIds.add(card.id);
    seenTexts.add(textKey);
    deduped.push({
      ...card,
      text: normalizedText
    });
  }

  await writeJson(CANDIDATE_PATH, deduped);
  console.log(`Deduped ${cards.length} cards down to ${deduped.length}.`);
}

async function exportApproved() {
  const cards = await readCandidates();
  const approved = cards.filter((card) => card.status === "approved");
  const promptCards = approved.filter((card) => card.type === "prompt").map(toPlayableCard);
  const answerCards = approved.filter((card) => card.type === "answer").map(toPlayableCard);
  const output = `import type { Card } from "./types";

export const promptCards: Card[] = ${JSON.stringify(promptCards, null, 2)};

export const answerCards: Card[] = ${JSON.stringify(answerCards, null, 2)};
`;

  await ensureParent(EXPORT_PATH);
  await writeFile(EXPORT_PATH, output, "utf8");
  console.log(`Exported ${promptCards.length} prompts and ${answerCards.length} answers to ${EXPORT_PATH}`);
}

function buildCandidates(type: CardType, count: number): CandidateCard[] {
  const cards: CandidateCard[] = [];
  const templates = type === "prompt" ? promptTemplates : answerTemplates;

  for (let index = 0; index < count; index += 1) {
    const bank = wordBanks[index % wordBanks.length];
    const template = templates[Math.floor(index / wordBanks.length) % templates.length];
    const text = fillTemplate(template, bank, index);
    const reviewNotes = reviewText(text);

    cards.push({
      id: `cf-${type === "prompt" ? "p" : "a"}-${String(index + 1).padStart(4, "0")}`,
      type,
      text,
      tags: [bank.tag, "uk-focused", "adult-only", "development-candidate"],
      intensity: bank.intensity,
      styleCategory: bank.styleCategory,
      createdAt: CREATED_AT,
      status: reviewNotes.length > 0 ? "rejected" : "candidate",
      reviewNotes
    });
  }

  return cards;
}

function fillTemplate(template: string, bank: WordBank, index: number) {
  return template
    .replaceAll("{subject}", pick(bank.subjects, index))
    .replaceAll("{place}", pick(bank.places, index + 1))
    .replaceAll("{object}", pick(bank.objects, index + 2))
    .replaceAll("{action}", pick(bank.actions, index + 3));
}

function pick(values: string[], index: number) {
  return values[index % values.length];
}

function reviewText(text: string) {
  const notes: string[] = [];

  for (const pattern of blockedPatterns) {
    if (pattern.test(text)) {
      notes.push(`Blocked by review pattern: ${pattern}`);
    }
  }

  return notes;
}

function toPlayableCard(card: CandidateCard): Card {
  return {
    id: card.id,
    type: card.type,
    text: card.text
  };
}

async function readCandidates() {
  const raw = await readFile(CANDIDATE_PATH, "utf8");
  return JSON.parse(raw) as CandidateCard[];
}

async function writeJson(path: string, data: unknown) {
  await ensureParent(path);
  await writeFile(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

async function ensureParent(path: string) {
  await mkdir(dirname(path), { recursive: true });
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
