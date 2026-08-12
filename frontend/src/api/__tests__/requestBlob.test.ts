import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestBlob, setUnauthorizedHandler, writeToken } from '../client';

const originalFetch = globalThis.fetch;

/**
 * Build a response the way the download endpoint answers.
 *
 * The body is a string rather than a `Blob`: jsdom's `Response` stringifies a
 * blob body to `[object Blob]` instead of reading its bytes, so constructing it
 * that way would assert on the polyfill rather than on the client.
 */
function pdfResponse(disposition?: string): Response {
  return new Response('%PDF-1.4', {
    status: 200,
    headers: {
      'Content-Type': 'application/pdf',
      ...(disposition ? { 'Content-Disposition': disposition } : {}),
    },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  setUnauthorizedHandler(() => {});
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

/**
 * Fetching a document rather than JSON.
 *
 * A sibling of `request`, not a variant of it: that one calls `response.json()`
 * unconditionally, which on a PDF throws and is swallowed by its own catch,
 * handing the caller a bogus object typed as whatever they asked for. These pin
 * the three places a binary path differs.
 */
describe('requestBlob', () => {
  it('returns the bytes and the name the server asked for', async () => {
    globalThis.fetch = vi.fn(async () =>
      pdfResponse('attachment; filename="FA-2026-000001.pdf"'),
    ) as unknown as typeof fetch;

    const { blob, filename } = await requestBlob('/api/v1/bills/b-1/document');

    expect(await blob.text()).toBe('%PDF-1.4');
    expect(filename).toBe('FA-2026-000001.pdf');
  });

  it('falls back to the caller’s name when the server sends none', async () => {
    // Derived at the call site the name would be the route path, and an
    // invoice would save as `document`.
    globalThis.fetch = vi.fn(async () => pdfResponse()) as unknown as typeof fetch;

    const { filename } = await requestBlob(
      '/api/v1/bills/b-1/document',
      'fallback.pdf',
    );

    expect(filename).toBe('fallback.pdf');
  });

  it('carries the bearer credential', async () => {
    // The objects are stored privately precisely so this endpoint is the only
    // way to them, which makes a download as credentialed as any other call.
    writeToken('token-1');
    const calls: RequestInit[] = [];
    globalThis.fetch = vi.fn(async (_url: unknown, init: RequestInit) => {
      calls.push(init);
      return pdfResponse();
    }) as unknown as typeof fetch;

    await requestBlob('/api/v1/bills/b-1/document');

    expect((calls[0]?.headers as Record<string, string>).Authorization).toBe(
      'Bearer token-1',
    );
  });

  it('reads the server’s own detail out of a failure', async () => {
    // **An error body is JSON but a success body is not.** The text is read
    // first and parsed inside a try, so a failure still reports what the server
    // said while a success never attempts to parse a document.
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: 'The document is unavailable.' }), {
          status: 503,
        }),
    ) as unknown as typeof fetch;

    await expect(requestBlob('/api/v1/bills/b-1/document')).rejects.toThrow(
      'The document is unavailable.',
    );
  });

  it('falls back to the status text on a non-JSON failure', async () => {
    // A proxy's own 502 page is markup, and the status is a better answer than
    // the markup would be.
    globalThis.fetch = vi.fn(
      async () =>
        new Response('<html>bad gateway</html>', {
          status: 502,
          statusText: 'Bad Gateway',
        }),
    ) as unknown as typeof fetch;

    await expect(requestBlob('/api/v1/bills/b-1/document')).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it('clears the session when the credential is rejected', async () => {
    // A token the server has stopped accepting is worse than no token: every
    // subsequent screen fails with a different symptom.
    writeToken('stale');
    const rejected = vi.fn();
    setUnauthorizedHandler(rejected);
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: 'Not authenticated.' }), {
          status: 401,
        }),
    ) as unknown as typeof fetch;

    await expect(requestBlob('/api/v1/bills/b-1/document')).rejects.toThrow();

    expect(rejected).toHaveBeenCalledOnce();
    expect(window.localStorage.getItem('simple-erp.token')).toBeNull();
  });
});
