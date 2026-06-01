export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  retryAfterSeconds?: number;
}

interface WindowState {
  count: number;
  windowStart: number;
}

export class RateLimiter {
  private windows = new Map<string, WindowState>();

  constructor(
    private readonly limit: number = 100,
    private readonly windowSeconds: number = 60,
  ) {}

  check(apiKey: string, nowMs: number = Date.now()): RateLimitResult {
    const state = this.windows.get(apiKey);
    const windowMs = this.windowSeconds * 1000;

    if (!state || nowMs - state.windowStart >= windowMs) {
      // New window
      this.windows.set(apiKey, { count: 1, windowStart: nowMs });
      return { allowed: true, remaining: this.limit - 1 };
    }

    if (state.count >= this.limit) {
      const windowEnd = state.windowStart + windowMs;
      const retryAfterSeconds = Math.ceil((windowEnd - nowMs) / 1000);
      return { allowed: false, remaining: 0, retryAfterSeconds };
    }

    // Bug: count is incremented even when request will be rejected (handled above,
    // but boundary case at exactly limit is mishandled — see tests)
    state.count += 1;
    return { allowed: true, remaining: this.limit - state.count };
  }
}
