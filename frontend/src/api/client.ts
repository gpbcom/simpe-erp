import type {
  AccessToken,
  CompanyRegistrationRequest,
  CompanyRegistrationResponse,
  User,
} from './types';

/**
 * Where the API lives.
 *
 * @remarks
 * **Read at runtime, not inlined at build time.** `VITE_API_BASE_URL` is a Vite
 * build argument, so a bundle built for staging carries staging's URL in its
 * JavaScript — which meant one image per environment and no way to promote the
 * digest that was actually tested. `/config.json` is a file nginx serves from
 * the same origin, replaced by a ConfigMap in the cluster and by a bind mount
 * in compose, so the *same* image is promoted dev → staging → production.
 *
 * The build argument is still honoured, and takes precedence, so `npm run dev`
 * and anything already setting it keep working.
 */
const BUILD_TIME_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;

let BASE_URL = BUILD_TIME_BASE_URL ?? '/api';

/** The shape of `/config.json`. */
interface RuntimeConfig {
  /** Where the API lives, as an absolute URL or a same-origin path. */
  api_base_url?: string;
}

/**
 * Read `/config.json` and point the client at whatever it names.
 *
 * @returns Nothing; the module-level base URL is replaced.
 *
 * @remarks
 * Awaited once before the app renders, so no request can be made against the
 * wrong origin. A missing or unreadable file leaves the build-time value
 * standing rather than failing to start: an application that refused to boot
 * because a *configuration* file was absent would be a worse failure than one
 * that fell back to the origin it was built for.
 *
 * **A build argument, when one was given, wins.** The production image ships no
 * `VITE_API_BASE_URL` at all — that is the whole point of reading the address at
 * runtime — so this file decides there and nothing is lost. Development is the
 * other way round: the compose overlay sets the variable to
 * `http://localhost:8000`, and the `/config.json` that ships in `public/` says
 * `/api`, which is right for nginx and wrong for Vite. Letting the file win
 * there pointed every request at the dev server, which has no `/api` and
 * answers 404 — a sign-in that failed with "an error occurred" because the
 * response was not the 401 the page knows how to describe.
 */
export async function loadRuntimeConfig(): Promise<void> {
  if (BUILD_TIME_BASE_URL) return;
  try {
    const response = await fetch('/config.json', { cache: 'no-store' });
    if (!response.ok) return;
    const config = (await response.json()) as RuntimeConfig;
    if (typeof config.api_base_url === 'string' && config.api_base_url.length > 0) {
      BASE_URL = config.api_base_url;
    }
  } catch {
    // Left as it was. See the remarks above: this must not stop the app.
  }
}

/** Where the session token is kept between page loads. */
const TOKEN_KEY = 'simple-erp.token';

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

/** A document fetched from the API, with the name it should be saved under. */
export interface BlobResponse {
  /** The bytes. */
  blob: Blob;
  /** The filename the server asked for it to be saved as. */
  filename: string;
}

/** Pull the filename out of a `Content-Disposition` header. */
const FILENAME_PATTERN = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i;

/**
 * Call the API for a document rather than for JSON.
 *
 * @param path - The path, beginning with a slash.
 * @param fallbackName - Saved-as name when the server names none.
 * @returns The bytes and the filename.
 * @throws ApiError - When the API answers 4xx or 5xx.
 *
 * @remarks
 * A sibling of `request`, not a variant of it. That one calls `response.json()`
 * unconditionally, which on a PDF throws and is then swallowed by its own
 * `catch`, handing the caller a bogus object typed as whatever they asked for.
 * A binary body needs its own path.
 *
 * Three differences beyond reading a blob, each of which bites if it is missed:
 *
 * 1. **An error body is JSON but a success body is not.** The text is read
 *    first and parsed inside a `try`, so a failure still reports the server's
 *    own `detail` while a success never attempts to parse a document.
 * 2. **The filename comes back with the bytes.** Derived at the call site it
 *    would be the route path, and an invoice would save as `document`.
 * 3. The bearer header and the 401 handling are shared with `request`, because
 *    a download is as much a credentialed call as any other — the objects are
 *    stored privately precisely so this endpoint is the only way to them.
 */
export async function requestBlob(
  path: string,
  fallbackName = 'document',
): Promise<BlobResponse> {
  const token = readToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const raw = await response.text().catch(() => '');
    let detail = response.statusText;
    let mustChangePassword = false;
    try {
      const body = JSON.parse(raw) as {
        detail?: string;
        must_change_password?: boolean;
      };
      detail = body.detail ?? detail;
      mustChangePassword = Boolean(body.must_change_password);
    } catch {
      // A non-JSON error body is possible — a proxy's own 502 page, say — and
      // the status text is a better answer than the page's markup.
    }
    if (response.status === 401) {
      clearToken();
      onUnauthorized();
    }
    throw new ApiError(response.status, detail, mustChangePassword);
  }

  const disposition = response.headers.get('Content-Disposition') ?? '';
  const matched = FILENAME_PATTERN.exec(disposition);
  return {
    blob: await response.blob(),
    filename: matched?.[1] ? decodeURIComponent(matched[1]) : fallbackName,
  };
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

/**
 * Found an agency and its first administrator.
 *
 * @param payload - The agency and its founder.
 * @returns The created agency and administrator.
 *
 * @remarks
 * Unauthenticated, and answered with 404 rather than 403 when the deployment
 * has not opted in — a 403 would confirm the feature exists and is merely
 * switched off. The caller signs in afterwards with the password it just sent.
 */
export function registerCompany(
  payload: CompanyRegistrationRequest,
): Promise<CompanyRegistrationResponse> {
  return request<CompanyRegistrationResponse>('/api/v1/companies/registration', {
    method: 'POST',
    json: payload,
  });
}

/** Report who the stored credential belongs to. */
export function fetchMe(): Promise<User> {
  return request<User>('/api/v1/auth/me');
}

/**
 * Open the notification event stream.
 *
 * @param onChanged - Called whenever the caller's notifications may have
 *   changed: once when the stream goes live, and again for every notification
 *   written while it is open.
 * @returns A function that closes the stream.
 *
 * @remarks
 * `EventSource` cannot set an `Authorization` header, so the stream is opened
 * with a short-lived token fetched from `/auth/stream-token` and passed in the
 * query string. That token lives one minute and is refused on every other
 * route, so a URL captured in a proxy log is worth nothing by the time anybody
 * reads it — which is why the session token is not used here.
 *
 * **The frames carry no data.** A `notification` frame says only that something
 * changed; the caller fetches what changed over HTTP. That keeps the database
 * the single source of truth, and means the same code path serves a live push
 * and a reader who has just signed back in.
 *
 * `ready` is reported too, and it is what makes the stream safe to rely on
 * without a poll behind it: it fires on the first connection *and* on every
 * reconnect, so anything written while the stream was down is picked up the
 * moment it comes back rather than up to a minute later.
 */
export function openNotificationStream(onChanged: () => void): () => void {
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
      source.addEventListener('ready', () => onChanged());
      source.addEventListener('notification', () => onChanged());
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
