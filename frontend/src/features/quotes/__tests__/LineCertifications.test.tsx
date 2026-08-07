import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LineCertifications } from '../LineCertifications';
import type { CertificationType } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const CATALOGUE: CertificationType[] = [
  {
    id: 'type-deaes',
    code: 'DEAES',
    label: 'Diplôme DEAES',
    description: null,
    is_active: true,
  },
  {
    id: 'type-sst',
    code: 'SST',
    label: 'Sauveteur Secouriste du Travail',
    description: null,
    is_active: true,
  },
];

describe('LineCertifications', () => {
  it('shows what the service requires while the line inherits', () => {
    render(
      <LineCertifications
        index={0}
        value={null}
        inherited={['DEAES']}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    // The label, not the code: "this visit needs DEAES" is something the
    // operator should be able to read without looking anything up.
    expect(screen.getByTestId('line-certification-0-DEAES')).toHaveTextContent(
      'Diplôme DEAES',
    );
  });

  it('says so plainly when the service requires nothing', () => {
    render(
      <LineCertifications
        index={0}
        value={null}
        inherited={[]}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('line-certifications-none-0')).toBeInTheDocument();
  });

  it('seeds the override from the inherited codes when it is taken over', async () => {
    const onChange = vi.fn();
    render(
      <LineCertifications
        index={0}
        value={null}
        inherited={['DEAES']}
        catalogue={CATALOGUE}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByTestId('line-certifications-inherit-0'));

    // Not an empty array: unticking "inherit" is the operator saying "let me
    // change this", not "require nothing". Starting empty would silently drop
    // a requirement they had not looked at yet.
    expect(onChange).toHaveBeenCalledWith(['DEAES']);
  });

  it('returns to inheriting when the box is ticked again', async () => {
    const onChange = vi.fn();
    render(
      <LineCertifications
        index={0}
        value={['SST']}
        inherited={['DEAES']}
        catalogue={CATALOGUE}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByTestId('line-certifications-inherit-0'));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('keeps an empty override distinct from inheriting', () => {
    render(
      <LineCertifications
        index={0}
        value={[]}
        inherited={['DEAES']}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    // An empty override means "this hour needs no qualification at all", which
    // is a real answer. It must not fall back to showing the service's chips —
    // that is the state the operator has just overridden.
    expect(screen.queryByTestId('line-certification-0-DEAES')).toBeNull();
    expect(screen.getByTestId('line-certifications-0')).toBeInTheDocument();
  });

  it('offers every catalogue entry once the line overrides', () => {
    render(
      <LineCertifications
        index={0}
        value={[]}
        inherited={[]}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    const select = screen.getByTestId('line-certifications-0');
    expect(select.querySelectorAll('option')).toHaveLength(2);
  });
});
