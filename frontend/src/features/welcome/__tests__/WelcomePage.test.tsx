import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { WelcomePage } from '../WelcomePage';
import type { User } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? `${key}(${Object.entries(values)
            .map(([name, value]) => `${name}=${String(value)}`)
            .join(',')})`
        : key,
  }),
}));

const navigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

const signOut = vi.fn();
let currentUser: User | null = null;

vi.mock('@/store/session', () => ({
  useSession: (selector: (state: unknown) => unknown) =>
    selector({ user: currentUser, signOut }),
}));

const USER = {
  id: 'user-1',
  email: 'nathalie@simple-erp.fr',
  full_name: 'Nathalie Blanchard',
  role: 'manager',
} as unknown as User;

const renderPage = () =>
  render(
    <MemoryRouter>
      <WelcomePage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  currentUser = null;
});

/**
 * The public landing page, and the one control on it that changes meaning.
 *
 * The page is reachable signed in *and* signed out, so the button has to say
 * what the visitor can do next rather than who they are. Getting that backwards
 * would offer "Sign in" to somebody already working, or sign somebody out who
 * only wanted to read what the product does.
 */
describe('WelcomePage', () => {
  it('describes every feature of the application', () => {
    // Nine cards, because the page's whole job is to answer "does this do my
    // job" — a short list would leave a reader guessing about the rest.
    renderPage();

    expect(screen.getByTestId('welcome-features').children).toHaveLength(9);
    expect(screen.getByTestId('feature-quote')).toBeInTheDocument();
    expect(screen.getByTestId('feature-planning')).toBeInTheDocument();
    expect(screen.getByTestId('feature-notification')).toBeInTheDocument();
    expect(screen.getByTestId('feature-interventionType')).toBeInTheDocument();
  });

  it('says what each role sees', () => {
    renderPage();

    expect(screen.getByTestId('welcome-roles').children).toHaveLength(3);
  });

  describe('when nobody is signed in', () => {
    it('offers a way in rather than a way out', () => {
      renderPage();

      expect(screen.getByTestId('welcome-session-button')).toHaveTextContent(
        'welcome.signIn',
      );
    });

    it('goes to the sign-in screen', async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(screen.getByTestId('welcome-session-button'));

      expect(navigate).toHaveBeenCalledWith('/login');
      expect(signOut).not.toHaveBeenCalled();
    });

    it('does not claim to know who is reading', () => {
      renderPage();

      expect(screen.queryByTestId('welcome-signed-in-as')).toBeNull();
    });
  });

  describe('when somebody is signed in', () => {
    beforeEach(() => {
      currentUser = USER;
    });

    it('offers a way out, and names them', () => {
      renderPage();

      expect(screen.getByTestId('welcome-session-button')).toHaveTextContent(
        'welcome.signOut',
      );
      expect(screen.getByTestId('welcome-signed-in-as')).toHaveTextContent(
        'Nathalie Blanchard',
      );
    });

    it('signs out and returns to this page', async () => {
      // Both halves matter. Signing out without navigating would leave the
      // signed-in routes rendering for a session that no longer exists.
      const user = userEvent.setup();
      renderPage();

      await user.click(screen.getByTestId('welcome-session-button'));

      expect(signOut).toHaveBeenCalledTimes(1);
      expect(navigate).toHaveBeenCalledWith('/welcome');
    });

    it('never sends a signed-in visitor to the sign-in screen', async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(screen.getByTestId('welcome-session-button'));

      expect(navigate).not.toHaveBeenCalledWith('/login');
    });
  });

  it('repeats the control at the foot of the page', async () => {
    // The page is long. A visitor who has read to the end should not have to
    // scroll back to the top to act on it.
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId('welcome-session-button-footer'));

    expect(navigate).toHaveBeenCalledWith('/login');
  });
});
