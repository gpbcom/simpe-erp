import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LineSkills } from '../LineSkills';
import type { SkillType } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const CATALOGUE: SkillType[] = [
  {
    id: 'type-leve',
    code: 'LEVE-PERSONNE',
    label: 'Manipulation d’un lève-personne',
    description: null,
    is_active: true,
  },
  {
    id: 'type-arabe',
    code: 'ARABE',
    label: 'Arabe parlé',
    description: null,
    is_active: true,
  },
];

describe('LineSkills', () => {
  it('shows what the service requires while the line inherits', () => {
    render(
      <LineSkills
        index={0}
        value={null}
        inherited={['LEVE-PERSONNE']}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    // The label, not the code: the operator should be able to read what the
    // visit needs without looking anything up.
    expect(screen.getByTestId('line-skill-0-LEVE-PERSONNE')).toHaveTextContent(
      'Manipulation d’un lève-personne',
    );
  });

  it('says so plainly when the service requires nothing', () => {
    render(
      <LineSkills
        index={0}
        value={null}
        inherited={[]}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('line-skills-none-0')).toBeInTheDocument();
  });

  it('seeds the override from the inherited codes when it is taken over', async () => {
    const onChange = vi.fn();
    render(
      <LineSkills
        index={0}
        value={null}
        inherited={['LEVE-PERSONNE']}
        catalogue={CATALOGUE}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByTestId('line-skills-inherit-0'));

    // Not an empty array: unticking "inherit" is the operator saying "let me
    // change this", not "require nothing". Starting empty would silently drop
    // a requirement they had not looked at yet.
    expect(onChange).toHaveBeenCalledWith(['LEVE-PERSONNE']);
  });

  it('returns to inheriting when the box is ticked again', async () => {
    const onChange = vi.fn();
    render(
      <LineSkills
        index={0}
        value={['ARABE']}
        inherited={['LEVE-PERSONNE']}
        catalogue={CATALOGUE}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByTestId('line-skills-inherit-0'));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('keeps an empty override distinct from inheriting', () => {
    render(
      <LineSkills
        index={0}
        value={[]}
        inherited={['LEVE-PERSONNE']}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    // An empty override means "this hour needs no skill at all", which is a
    // real answer. It must not fall back to showing the service's chips — that
    // is the state the operator has just overridden.
    expect(screen.queryByTestId('line-skill-0-LEVE-PERSONNE')).toBeNull();
    expect(screen.getByTestId('line-skills-0')).toBeInTheDocument();
  });

  it('offers every catalogue entry once the line overrides', () => {
    render(
      <LineSkills
        index={0}
        value={[]}
        inherited={[]}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('line-skills-0').querySelectorAll('option')).toHaveLength(
      2,
    );
  });

  it('keeps its own test ids distinct from the certification control', () => {
    // The two sit on the same line, so ids that collided would make the GUI
    // campaign operate whichever the DOM happened to yield first — and the two
    // requirements are satisfied from different places.
    render(
      <LineSkills
        index={0}
        value={[]}
        inherited={[]}
        catalogue={CATALOGUE}
        onChange={vi.fn()}
      />,
    );

    expect(screen.queryByTestId('line-certifications-0')).toBeNull();
  });
});
