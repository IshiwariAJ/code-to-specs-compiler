// Kitchen sink TypeScript sample.
// Purpose: compile supported constructs and expose unsupported constructs as warnings.

import { readFile } from "fs/promises";

const MAX_POINTS = 1000;
const PREMIUM_THRESHOLD = 100000;
let auditCounter = 0;

type UserStatus = "ACTIVE" | "INACTIVE" | "BANNED";
type BenefitLevel = "premium" | "standard" | "basic";

interface Purchase {
  price: number;
  category?: string;
}

interface User {
  id: string;
  status: UserStatus;
  rank: string;
  purchaseHistory: Purchase[];
  metadata?: Record<string, unknown>;
}

interface BenefitResult {
  points: number;
  message: string;
  level: BenefitLevel;
}

class AuditLog {
  private entries: string[] = [];

  add(message: string): void {
    this.entries.push(message);
  }
}

/**
 * Supported-heavy function: guards, loops, data transforms, try/catch/finally and condition chains.
 */
async function calculateUserBenefit(
  user: User,
  options: { configPath?: string; dryRun?: boolean } = {},
  ...tags: string[]
): Promise<BenefitResult> {
  if (user.status !== "ACTIVE") {
    throw new Error("inactive user");
  }

  let totalAmount = 0;
  for (const history of user.purchaseHistory) {
    totalAmount += history.price;
  }

  for (let i = 0; i < tags.length; i++) {
    console.log(tags[i]);
  }

  try {
    const configText = await readFile(options.configPath ?? "config.json", "utf8");
    console.log(configText);
  } catch (error) {
    console.error(error);
    throw error;
  } finally {
    auditCounter += 1;
    console.log("benefit calculation finished");
  }

  if (options.dryRun) {
    return { points: 0, message: "dry run", level: "basic" };
  } else if (totalAmount >= PREMIUM_THRESHOLD && user.rank === "Gold") {
    return { points: MAX_POINTS, message: "premium benefit", level: "premium" };
  } else if (totalAmount >= 50000) {
    return { points: 500, message: "standard benefit", level: "standard" };
  } else {
    return { points: 100, message: "basic benefit", level: "basic" };
  }
}

/**
 * Unsupported-heavy function: these constructs should be visible as extraction warnings today.
 */
function inspectUnsupportedFlow(user: User, values: number[]): number {
  let index = 0;
  let total = 0;

  while (index < values.length) {
    total += values[index];
    index += 1;
  }

  do {
    total -= 1;
  } while (total > 1000);

  switch (user.status) {
    case "ACTIVE":
      total += 10;
      break;
    case "BANNED":
      total -= 100;
      break;
    default:
      total += 0;
  }

  for (const key in user.metadata ?? {}) {
    console.log(key);
  }

  const [first = 0, ...rest] = values;
  const { rank = "None" } = user;
  const normalized = rest.map((value) => value * 2).filter((value) => value > first);
  const label = total > 0 ? `rank:${rank}` : "none";
  console.log(label);

  return normalized.reduce((sum, value) => sum + value, total);
}

const arrowBenefit = (value: number): number => (value > 0 ? value : 0);

