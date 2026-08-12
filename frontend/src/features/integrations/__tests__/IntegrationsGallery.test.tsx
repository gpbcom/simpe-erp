import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { IntegrationsGallery } from '../IntegrationsGallery';
import { EInvoicingWarning } from '../EInvoicingWarning';
import type { IntegrationCard } from '@/api/types';

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

const enable = vi.fn();
const disable = vi.fn();
let cards: IntegrationCard[] = [];
let loading = false;

vi.mock('@/api/queries', () => ({
  useIntegrations: () => ({ data: cards, isLoading: loading }),
  useEnableIntegration: () => ({ mutate: enable, isPending: false, isError: false }),
  useDisableIntegration: () => ({ mutate: disable, isPending: false }),
  useCheckIntegration: () => ({ mutate: vi.fn(), isPending: false }),
}));

const card = (over: Partial<IntegrationCard> = {}): IntegrationCard => ({
  provider: 'b2brouter',
  name: 'B2Brouter',
  home_url: 'https://www.b2brouter.net/fr/',
  documentation_url: 'https://docs.b2brouter.net/',
  coverage: ['invoice', 'payment-report', 'chorus-pro'],
  required_fields: ['api_key', 'account_id'],
  documentation_verified: true,
  configured: false,
  enabled: false,
  credential_hint: '',
  last_checked_at: null,
  last_check_error: null,
  ...over,
});

const FOUR: IntegrationCard[] = [
  card(),
  card({
    provider: 'storecove',
    name: 'Storecove',
    coverage: ['invoice', 'payment-report'],
    required_fields: ['api_key', 'legal_entity_id'],
  }),
  card({ provider: 'invopop', name: 'Invopop', required_fields: ['api_key'] }),
  card({
    provider: 'iopole',
    name: 'Iopole',
    required_fields: ['api_key'],
    documentation_verified: false,
  }),
];

const renderGallery = () =>
  render(
    <MemoryRouter>
      <IntegrationsGallery />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  cards = FOUR;
  loading = false;
});

/**
 * The gallery, and the two things it must never get wrong: showing a secret,
 * and letting an agency believe it is connected when it is not.
 */
describe('IntegrationsGallery', () => {
  it('offers every certified platform', () => {
    // Every platform, configured or not — a list of only what is already
    // connected would be empty on the screen whose job is to connect one.
    renderGallery();

    expect(screen.getByTestId('integrations-grid').children).toHaveLength(4);
    expect(screen.getByTestId('integration-card-b2brouter')).toBeInTheDocument();
    expect(screen.getByTestId('integration-card-iopole')).toBeInTheDocument();
  });

  it('carries the screenshot’s controls', () => {
    renderGallery();

    expect(screen.getByTestId('integrations-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('integrations-sort')).toBeInTheDocument();
    expect(screen.getByTestId('integrations-search')).toBeInTheDocument();
  });

  it('does not paginate four platforms', () => {
    // **The one deliberate departure from the reference.** A pagination bar
    // whose every state is identical is furniture, not a control.
    renderGallery();

    expect(screen.queryByTestId('integrations-pagination')).toBeNull();
  });

  it('filters to the platforms that reach public bodies', async () => {
    // The filter that actually matters: an agency invoicing a conseil
    // départemental has to know which platforms reach Chorus Pro before it
    // picks one, not after.
    const user = userEvent.setup();
    renderGallery();

    await user.click(screen.getByTestId('integrations-tab-public'));

    expect(screen.getByTestId('integrations-grid').children).toHaveLength(3);
    expect(screen.queryByTestId('integration-card-storecove')).toBeNull();
  });

  it('finds a platform by name', async () => {
    const user = userEvent.setup();
    renderGallery();

    await user.type(screen.getByTestId('integrations-search'), 'iopo');

    expect(screen.getByTestId('integrations-grid').children).toHaveLength(1);
  });

  it('says which platform’s documentation could not be read', () => {
    // A gallery offering all four as equals would be lying by omission.
    renderGallery();

    expect(screen.getByTestId('integration-unverified-iopole')).toBeInTheDocument();
    expect(screen.queryByTestId('integration-unverified-invopop')).toBeNull();
  });

  it('marks the one platform that is transmitting', () => {
    cards = [card({ enabled: true, configured: true }), ...FOUR.slice(1)];

    renderGallery();

    expect(screen.getByTestId('integration-enabled-b2brouter')).toBeInTheDocument();
    expect(screen.queryByTestId('integration-enabled-storecove')).toBeNull();
  });

  it('reports a credential that has stopped working', () => {
    // A key rotated at the far end must surface here rather than as an invoice
    // that silently never left.
    cards = [
      card({ enabled: true, configured: true, last_check_error: '401' }),
      ...FOUR.slice(1),
    ];

    renderGallery();

    expect(screen.getByTestId('integration-error-b2brouter')).toBeInTheDocument();
  });

  describe('the warning that nothing is connected', () => {
    it('shows when the agency cannot transmit', () => {
      // Electronic invoicing is an obligation, so "nothing connected" is a
      // state the screen says out loud rather than renders as an empty list.
      render(
        <MemoryRouter>
          <EInvoicingWarning />
        </MemoryRouter>,
      );

      expect(screen.getByTestId('einvoicing-warning')).toBeInTheDocument();
    });

    it('disappears once a platform is enabled', () => {
      cards = [card({ enabled: true }), ...FOUR.slice(1)];

      render(
        <MemoryRouter>
          <EInvoicingWarning />
        </MemoryRouter>,
      );

      expect(screen.queryByTestId('einvoicing-warning')).toBeNull();
    });

    it('does not flash while the answer is unknown', () => {
      // An agency that *has* connected a platform must never be told, even for
      // a moment, that it has not.
      loading = true;

      render(
        <MemoryRouter>
          <EInvoicingWarning />
        </MemoryRouter>,
      );

      expect(screen.queryByTestId('einvoicing-warning')).toBeNull();
    });
  });

  describe('connecting a platform', () => {
    it('takes two clicks and a paste', async () => {
      // Requirement 5, asserted as a count: the card opens the dialog, the
      // fields are filled, the button saves. No separate test step, because
      // the server proves the key as part of enabling.
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-invopop'));
      await user.type(screen.getByTestId('integration-field-api_key'), 'sk_live_x');
      await user.click(screen.getByTestId('integration-save'));

      expect(enable).toHaveBeenCalledTimes(1);
      expect(enable).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'invopop',
          body: expect.objectContaining({ api_key: 'sk_live_x' }),
        }),
        expect.anything(),
      );
    });

    it('asks only for the fields the platform needs', async () => {
      // Storecove wants a legal-entity reference from its own console;
      // Invopop wants a key alone. Three empty boxes would raise a question
      // about which of them matter.
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-storecove'));

      expect(
        screen.getByTestId('integration-field-legal_entity_id'),
      ).toBeInTheDocument();
      expect(screen.queryByTestId('integration-field-account_id')).toBeNull();
    });

    it('will not save until every required field is filled', async () => {
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-b2brouter'));

      expect(screen.getByTestId('integration-save')).toBeDisabled();
    });

    it('warns inside the dialog about the unverified platform', async () => {
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-iopole'));

      expect(screen.getByTestId('integration-dialog-unverified')).toBeInTheDocument();
    });

    it('shows the masked tail of a key already stored, never the key', async () => {
      // The server has no endpoint that returns the secret; this is the most
      // a screen can honestly show.
      cards = [card({ configured: true, credential_hint: '…cdef' }), ...FOUR.slice(1)];
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-b2brouter'));

      expect(screen.getByTestId('integration-dialog-hint')).toHaveTextContent('…cdef');
    });

    it('offers to disconnect the platform that is transmitting', async () => {
      const user = userEvent.setup();
      cards = [card({ enabled: true, configured: true }), ...FOUR.slice(1)];
      renderGallery();

      await user.click(screen.getByTestId('integration-card-b2brouter'));
      await user.click(screen.getByTestId('integration-disable'));

      expect(disable).toHaveBeenCalledWith('b2brouter', expect.anything());
    });

    it('does not offer to disconnect one that is not', async () => {
      const user = userEvent.setup();
      renderGallery();

      await user.click(screen.getByTestId('integration-card-invopop'));

      expect(screen.queryByTestId('integration-disable')).toBeNull();
    });
  });
});
