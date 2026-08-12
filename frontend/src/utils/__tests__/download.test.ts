import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { saveBlob } from '../download';

beforeEach(() => {
  // jsdom implements no object-URL store at all, so the two methods have to
  // exist before they can be spied on. Defining them here rather than in the
  // shared setup keeps the polyfill next to the only code that needs it.
  Object.defineProperty(URL, 'createObjectURL', {
    value: () => 'blob:stub',
    writable: true,
    configurable: true,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: () => {},
    writable: true,
    configurable: true,
  });
});

afterEach(() => vi.restoreAllMocks());

/**
 * Handing a fetched document to the browser.
 *
 * The revoke is the part worth pinning: a blob URL keeps its bytes alive for as
 * long as the document does, so a manager downloading a month of invoices
 * without it holds every one of them in memory until they navigate away.
 */
describe('saveBlob', () => {
  it('saves under the name the server asked for', () => {
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:invoice');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.download);
    });

    saveBlob(new Blob(['%PDF-1.4']), 'FA-2026-000001.pdf');

    expect(create).toHaveBeenCalledOnce();
    expect(clicked).toEqual(['FA-2026-000001.pdf']);
  });

  it('releases the object URL immediately', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:invoice');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    saveBlob(new Blob(['%PDF-1.4']), 'FA-2026-000001.pdf');

    expect(revoke).toHaveBeenCalledWith('blob:invoice');
  });

  it('leaves nothing behind in the document', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:invoice');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    saveBlob(new Blob(['%PDF-1.4']), 'FA-2026-000001.pdf');

    expect(document.querySelectorAll('a')).toHaveLength(0);
  });
});
