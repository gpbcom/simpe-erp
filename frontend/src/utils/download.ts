/**
 * Hand a fetched document to the browser as a download.
 *
 * @param blob - The bytes.
 * @param filename - The name to save it under.
 *
 * @remarks
 * The object URL is revoked immediately after the click. A blob URL keeps its
 * bytes alive for as long as the document does, so a manager downloading a
 * month of invoices without this would hold every one of them in memory until
 * they navigated away.
 *
 * The anchor is created, clicked and removed rather than rendered: this is
 * called from a mutation's `onSuccess`, where there is no element to attach a
 * real link to and no render pass to wait for.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
