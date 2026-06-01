import { RateLimiter } from '../src/rateLimiter';

describe('RateLimiter', () => {
  it('allows a request when under the limit', () => {
    const limiter = new RateLimiter(5, 60);
    const result = limiter.check('key-1', 1000);
    expect(result.allowed).toBe(true);
  });

  it('rejects a request when over the limit', () => {
    const limiter = new RateLimiter(2, 60);
    limiter.check('key-1', 1000);
    limiter.check('key-1', 1000);
    const result = limiter.check('key-1', 1000);
    expect(result.allowed).toBe(false);
  });

  it('returns retryAfterSeconds when rejected', () => {
    const limiter = new RateLimiter(1, 60);
    limiter.check('key-1', 0);
    const result = limiter.check('key-1', 1000);
    expect(result.retryAfterSeconds).toBeGreaterThan(0);
  });

  // Missing: test that exactly at the limit (count === limit) is permitted, not rejected
  // Missing: test that two keys have independent counters
  // Missing: test that window resets after windowSeconds
  // Missing: test that rejected requests do not increment the counter
});
