import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * The marks carrying the wordmark, and the frame each has to fit inside.
 *
 * The two `docs/assets` files are the README's variants. They are checked here
 * rather than left uncovered because they are the same artwork with a different
 * ink, and the failure they share is the one this file exists for.
 */
const WORDMARKS = [
  '../logo-full.svg',
  '../../../../../docs/assets/logo-light.svg',
  '../../../../../docs/assets/logo-dark.svg',
] as const;

/** The mark-only files: no wordmark, so nothing here to clip. */
const MARKS = ['../logo-mark.svg', '../../../../public/favicon.svg'] as const;

/**
 * Read one of the brand files.
 *
 * @param relative - Path relative to this test file.
 * @returns The file's contents.
 */
function read(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
}

/**
 * Return a viewBox's width.
 *
 * @param svg - The document.
 * @returns The width in user units.
 */
function frameWidth(svg: string): number {
  const match = /viewBox="0 0 ([\d.]+) [\d.]+"/.exec(svg);
  expect(match, 'the file declares a viewBox starting at the origin').not.toBeNull();
  return Number(match![1]);
}

describe('the brand marks', () => {
  /**
   * **The regression this file exists for.**
   *
   * The wordmark's drawn width depends on which font actually resolves. `Inter`
   * is named first and is loaded nowhere, so a browser falls back to
   * `system-ui` and a converter falls back to something else again. A frame cut
   * to fit one of them clips the others — and it did: the application header
   * rendered "SimpleER".
   *
   * `textLength` pins the advance width regardless of the font, which is what
   * makes a tight frame safe. Asserting it is present is the cheap half;
   * asserting it fits inside the frame is the half that catches somebody
   * narrowing the viewBox again.
   */
  it.each(WORDMARKS)('%s pins its wordmark and fits the frame', (file) => {
    const svg = read(file);
    const width = frameWidth(svg);
    const text = /<text[^>]*textLength="([\d.]+)"[^>]*>/.exec(svg);

    expect(
      text,
      'the wordmark carries textLength, so the font cannot widen it',
    ).not.toBeNull();

    const start = Number(/<text x="([\d.]+)"/.exec(svg)![1]);
    const advance = Number(text![1]);

    expect(svg).toContain('lengthAdjust="spacingAndGlyphs"');
    expect(start + advance).toBeLessThanOrEqual(width);
  });

  it.each(WORDMARKS)('%s spells the product name in full', (file) => {
    // Guards the other way a wordmark goes wrong: not clipped by the frame, but
    // truncated in the source. Reading the file is the only check that sees it,
    // because a short name renders perfectly happily.
    expect(read(file)).toContain('>SimpleERP<');
  });

  it.each([...WORDMARKS, ...MARKS])(
    '%s resolves every gradient it paints with',
    (file) => {
      // A `url(#id)` whose id was renamed leaves the shape unpainted rather than
      // erroring. That happened once already, during the rename: the gradient
      // vanished and only the amber hand-arcs drew.
      const svg = read(file);
      const defined = new Set(
        [...svg.matchAll(/<linearGradient id="([^"]+)"/g)].map((match) => match[1]),
      );
      const used = [...svg.matchAll(/url\(#([^)]+)\)/g)].map((match) => match[1]);

      for (const reference of used) {
        expect(defined, `${reference} is painted with but never defined`).toContain(
          reference,
        );
      }
    },
  );
});
