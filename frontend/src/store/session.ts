import { create } from 'zustand';
import {
  clearToken,
  fetchMe,
  readToken,
  setUnauthorizedHandler,
  signIn as apiSignIn,
} from '@/api/client';
import type { User, UserRole } from '@/api/types';
import { setLanguage } from '@/i18n';

interface SessionState {
  /** The signed-in account, once resolved. */
  user: User | null;
  /** Whether the initial token check is still running. */
  loading: boolean;
  /** Sign in and load the account. */
  signIn: (email: string, password: string) => Promise<void>;
  /** Forget the session. */
  signOut: () => void;
  /** Resolve the stored token, if there is one. */
  restore: () => Promise<void>;
  /** Re-read the account, after a password change for instance. */
  refresh: () => Promise<void>;
}

/**
 * Adopt the account's stored language, so the interface opens in it.
 *
 * @param user - The account just resolved from the server.
 * @returns The same account, unchanged.
 *
 * @remarks
 * The server holds the preference because the quotes emailed to customers
 * are generated from it by a background webhook, which has no browser to
 * read a `localStorage` value out of. Adopting it here is what keeps the
 * two ends honest: signing in on a colleague's laptop should not leave the
 * screen in their language while every document goes out in yours.
 *
 * `setLanguage` writes `localStorage` too, so the choice still survives a
 * reload made before the session has been restored.
 */
function adopt(user: User): User {
  if (user.language) setLanguage(user.language);
  return user;
}

/**
 * The signed-in account, and how to change it.
 *
 * @remarks
 * Deliberately the *only* client-side state kept outside TanStack Query.
 * Everything else on screen is server state, and duplicating it into a store
 * is how two components end up disagreeing about the same quote.
 */
export const useSession = create<SessionState>((set) => ({
  user: null,
  loading: true,

  signIn: async (email, password) => {
    await apiSignIn(email, password);
    set({ user: adopt(await fetchMe()) });
  },

  signOut: () => {
    clearToken();
    set({ user: null });
  },

  restore: async () => {
    if (!readToken()) {
      set({ user: null, loading: false });
      return;
    }
    try {
      set({ user: adopt(await fetchMe()), loading: false });
    } catch {
      // A token the server no longer accepts is worse than none: every screen
      // would fail with a different symptom instead of one clear sign-in page.
      clearToken();
      set({ user: null, loading: false });
    }
  },

  refresh: async () => {
    if (!readToken()) return;
    set({ user: await fetchMe() });
  },
}));

// Registered once, at module load: a 401 anywhere drops the session, so the
// router's guard sends the user to the sign-in page rather than leaving them on
// a screen that silently shows nothing.
setUnauthorizedHandler(() => useSession.setState({ user: null }));

/**
 * Whether a role ranks at or above another.
 *
 * @param role - The role held.
 * @param minimum - The lowest role that satisfies the check.
 * @returns Whether the check passes.
 *
 * @remarks
 * Mirrors `UserRole.has_at_least` on the server. This is for *drawing* — hiding
 * a button the caller may not use — and never for deciding: the server checks
 * every request regardless, because anything decided here can be edited in a
 * browser console.
 */
export function hasAtLeast(role: UserRole | undefined, minimum: UserRole): boolean {
  const rank = { hca: 0, manager: 1, admin: 2 };
  return role !== undefined && rank[role] >= rank[minimum];
}
