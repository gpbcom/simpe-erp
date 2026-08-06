import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { QuoteStatusChip } from '../QuoteStatusChip';
import '@/i18n';

describe('QuoteStatusChip', () => {
  it('labels a quote awaiting validation in French', () => {
    render(<QuoteStatusChip status="pending-validation" />);

    expect(screen.getByText('À valider')).toBeInTheDocument();
  });

  it('gives the awaiting-validation status its own colour', () => {
    // The one status that is waiting on a *person* has to stand out from the
    // five that are not. If it renders like a draft, the manager's validation
    // queue is invisible in a list of ninety quotes.
    const { container } = render(<QuoteStatusChip status="pending-validation" />);

    expect(container.querySelector('.MuiChip-colorWarning')).not.toBeNull();
  });

  it('draws a draft as an outline rather than a filled chip', () => {
    const { container } = render(<QuoteStatusChip status="draft" />);

    expect(container.querySelector('.MuiChip-outlined')).not.toBeNull();
  });
});
