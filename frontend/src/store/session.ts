import { create } from 'zustand';
import {
  clearToken,
  fetchMe,
  readToken,
  setUnauthorizedHandler,
  signIn as apiSignIn,
} from '@/api/client';
import type { SignInSpace, User, UserRole } from '@/api/types';
import { setLanguage } from '@/i18n';

/**
 * Raised when an account signs in to the space it does not belong to.
 *
 * @remarks
 * A distinct error rather than a generic failure, because the screen has
 * something specific and useful to say: the credentials were right, the *space*
 * was wrong. Reported as "invalid credentials" it would send somebody to reset
 * a password that works perfectly.
 */
export class WrongSpaceError extends Error {
  /** The space the account actually belongs to. */
  readonly belongsTo: SignInSpace;

  /**
   * Build the error.
   *
   * @param belongsTo - The space the account actually belongs to.
   */
  constructor(belongsTo: SignInSpace) {
    super(`This account belongs to the ${belongsTo} space.`);
    this.name = 'WrongSpaceError';
    this.belongsTo = belongsTo;
  }
}

interface SessionState {
  user: User | null;
  loading: boolean;
  /**
   * Sign in to a chosen space.
   *
   * @remarks
   * The space is validated **after** authentication, so an employee account
   * signing in as a customer is refused with a message naming the mistake
   * rather than landing somewhere confusing. The check is a courtesy, not a
   * control — the credential decides what the server will serve either way.
   */
  signIn: (email: string, password: string, space?: SignInSpace) => Promise<void>;
  signOut: () => void;
  restore: () => Promise<void>;
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

  signIn: async (email, password, space = 'employee') => {
    await apiSignIn(email, password);
    const user = adopt(await fetchMe());
    const belongs = space === 'customer' ? !isStaff(user.role) : isStaff(user.role);
    if (!belongs) {
      clearToken();
      throw new WrongSpaceError(isStaff(user.role) ? 'employee' : 'customer');
    }
    set({ user });
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
      clearToken();
      set({ user: null, loading: false });
    }
  },

  refresh: async () => {
    if (!readToken()) return;
    set({ user: await fetchMe() });
  },
}));

setUnauthorizedHandler(() => useSession.setState({ user: null }));

const STAFF_RANK = { hca: 0, manager: 1, admin: 2 } as const;

export type StaffRole = keyof typeof STAFF_RANK;

/**
 * Whether a role is one the agency employs.
 *
 * @param role - The role held.
 * @returns Whether it is on the staff ladder.
 *
 * @remarks
 * The one safe way to ask the question that separates the two axes, and a type
 * guard so `hasAtLeast` below can only be reached with a rankable role.
 */
export function isStaff(role: UserRole | undefined): role is StaffRole {
  return role !== undefined && role in STAFF_RANK;
}

/**
 * Whether a role ranks at or above another.
 *
 * @param role - The role held.
 * @param minimum - The lowest **staff** role that satisfies the check.
 * @returns Whether the check passes. A customer is always `false`.
 *
 * @remarks
 * Mirrors `UserRole.has_at_least` on the server. This is for *drawing* — hiding
 * a button the caller may not use — and never for deciding: the server checks
 * every request regardless, because anything decided here can be edited in a
 * browser console.
 *
 * **`minimum` is typed `StaffRole`, not `UserRole`, and that is the control.**
 * A customer is not above or below an assistant — they are a different axis —
 * so `hasAtLeast(role, 'customer')` has no correct answer: below the ladder it
 * is true for every employee, which admits staff to a household's private
 * space. Typing the parameter makes the call a **compile error** rather than a
 * silent privilege bug. The portal uses `CustomerRoute`, which compares by
 * identity. The server refuses to rank a customer at all.
 *
 * A customer *holding* the role answers `false` for every staff check, which is
 * the right answer to "may they see the agency's screens".
 */
export function hasAtLeast(role: UserRole | undefined, minimum: StaffRole): boolean {
  if (!isStaff(role)) return false;
  return STAFF_RANK[role] >= STAFF_RANK[minimum];
}
