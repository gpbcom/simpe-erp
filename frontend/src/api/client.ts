import type { AccessToken, User } from './types';

/** Where the API lives. Inlined by Vite at build time. */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? 'http://localhost:8000';

/** Where the session token is kept between page loads. */
const TOKEN_KEY = 'rt-erp.token';

/** An error carrying the status and message the API answered with. */
export class ApiError extends Error {
  /** The HTTP status. */
  readonly status: number;
  /** Whether the account must change its password before doing anything else. */
  readonly mustChangePassword: boolean;

  /**
   * @param status - The HTTP status the API answered with.
   * @param detail - The message from the `detail` field.
   * @param mustChangePassword - Whether the 403 was the password-change gate.
   */
  constructor(status: number, detail: string, mustChangePassword = false) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.mustChangePassword = mustChangePassword;
  }
}

/** Read the stored session token. */
export function readToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

/** Store the session token. */
export function writeToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

/** Forget the session token. */
export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** What happens when the API rejects the stored credential. */
type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler = () => {};

/**
 * Register what to do when the API answers 401.
 *
 * @param handler - Called once per rejected request.
 *
 * @remarks
 * Set by the session store rather than imported by it, so this module stays
 * free of React and can be used from a test or a script.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler;
}

/**
 * Call the API.
 *
 * @param path - The path, beginning with a slash.
 * @param init - Anything `fetch` accepts, plus a JSON body.
 * @returns The parsed response body.
 * @throws ApiError - When the API answers 4xx or 5xx.
 *
 * @remarks
 * The bearer header is attached **here**, because the generated-client route
 * cannot: FastAPI declares no security scheme, so nothing in the schema says
 * these routes need a credential.
 *
 * A 401 clears the session and notifies the store — a token that the server has
 * stopped accepting is worse than no token, because every subsequent screen
 * fails with a different symptom. A 403 carrying `must_change_password` is
 * distinguished from an ordinary refusal, since it is the one case a client
 * should react to by navigating rather than by apologising.
 */
export async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const token = readToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    ...(json !== undefined ? { body: JSON.stringify(json) } : {}),
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response
    .json()
    .catch(() => ({ detail: response.statusText }));

  if (!response.ok) {
    const body = payload as { detail?: string; must_change_password?: boolean };
    if (response.status === 401) {
      clearToken();
      onUnauthorized();
    }
    throw new ApiError(
      response.status,
      body.detail ?? 'Request failed',
      Boolean(body.must_change_password),
    );
  }
  return payload as T;
}

/** Sign in and store the resulting token. */
export async function signIn(email: string, password: string): Promise<AccessToken> {
  const token = await request<AccessToken>('/api/v1/auth/login', {
    method: 'POST',
    json: { email, password },
  });
  writeToken(token.access_token);
  return token;
}

/** Report who the stored credential belongs to. */
export function fetchMe(): Promise<User> {
  return request<User>('/api/v1/auth/me');
}

/**
 * Open the notification event stream.
 *
 * @param onNotification - Called for every notification frame.
 * @returns A function that closes the stream.
 *
 * @remarks
 * `EventSource` cannot set an `Authorization` header, so the stream is opened
 * with a short-lived token fetched from `/auth/stream-token` and passed in the
 * query string. That token lives one minute and is refused on every other
 * route, so a URL captured in a proxy log is worth nothing by the time anybody
 * reads it — which is why the session token is not used here.
 */
export function openNotificationStream(
  onNotification: (payload: unknown) => void,
): () => void {
  let source: EventSource | null = null;
  let closed = false;

  const connect = async (): Promise<void> => {
    if (closed) return;
    try {
      const streamToken = await request<AccessToken>('/api/v1/auth/stream-token', {
        method: 'POST',
      });
      if (closed) return;
      source = new EventSource(
        `${BASE_URL}/api/v1/notifications/stream?token=${encodeURIComponent(
          streamToken.access_token,
        )}`,
      );
      source.addEventListener('notification', (event) => {
        onNotification(JSON.parse((event as MessageEvent<string>).data));
      });
      source.onerror = () => {
        // The token expires after a minute, so a reconnect needs a fresh one —
        // EventSource's own retry would keep replaying the dead one for ever.
        source?.close();
        source = null;
        if (!closed) window.setTimeout(() => void connect(), 5000);
      };
    } catch {
      if (!closed) window.setTimeout(() => void connect(), 15000);
    }
  };

  void connect();
  return () => {
    closed = true;
    source?.close();
  };
}
