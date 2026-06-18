import { randomBytes } from "crypto";

export function newToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

const PAIR_TTL_MS = 10 * 60 * 1000;

export function isExpired(createdAt: Date, ttlMs = PAIR_TTL_MS): boolean {
  return Date.now() - createdAt.getTime() > ttlMs;
}
