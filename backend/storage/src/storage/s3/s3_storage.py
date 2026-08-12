from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

# Third-party imports
import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

# First-party imports
from models.configuration.s3_config import S3Config
from storage.s3.exceptions import (
    MTS3BucketUnavailable,
    MTS3DeleteFailed,
    MTS3EmptyPayload,
    MTS3PayloadTooLarge,
    MTS3UnsupportedContentType,
    MTS3UploadFailed,
)


class S3Storage:
    """Stores and removes assistant photographs and company logos in a bucket.

    Attributes:
        CONTENT_TYPE_EXTENSIONS (ClassVar[Dict[str, str]]): File extension per
            accepted content type.
        MAGIC_SIGNATURES (ClassVar[Tuple[Tuple[bytes, str], ...]]): Leading
            bytes identifying each accepted image format.
        CACHE_CONTROL (ClassVar[str]): Cache header written with every image.
        DOCUMENT_SIGNATURE (ClassVar[bytes]): Leading bytes identifying a
            PDF.
        DOCUMENT_CONTENT_TYPE (ClassVar[str]): The only type stored under
            the invoice prefix.
        DOCUMENT_CACHE_CONTROL (ClassVar[str]): Cache header written with
            every invoice.
        config (S3Config): Bucket and credential settings.
        logger (Logger): Logger for object-store operations.

    Notes:
        - ``boto3`` is synchronous, so every call is pushed onto a worker thread
          with :func:`asyncio.to_thread`. Calling it directly would block the
          event loop for the whole duration of the transfer, stalling every other
          request in the process.
        - The content type is decided from the file's own leading bytes, not from
          the ``Content-Type`` header the client sent. A client controls that
          header completely, and a bucket serving attacker-chosen content types
          is how a stored file becomes a stored cross-site-scripting payload.
        - The object key is generated, never taken from the upload's filename. A
          filename can carry ``../`` or a leading slash, and using it would let a
          caller write outside the photo prefix.
        - **Two prefixes, one set of rules.** Photographs and logos are written
          under separate prefixes so a cleanup of one cannot reach the other,
          but they share the sniffing, the size limit and the key resolution.
          A second class for logos would have meant a second copy of the checks
          that make this one safe.
        - **Invoices are the exception, and deliberately so.** They live under a
          third prefix with their own sniffer, their own cache headers and no
          public URL at all: the two image paths exist to serve a browser, and
          an invoice is only ever read back server-side and streamed through an
          authenticated endpoint. Widening the image allow-list to admit a
          document would have admitted it for photographs too — the shared rule
          is the thing that must not be shared here.
    """

    CONTENT_TYPE_EXTENSIONS: ClassVar[Dict[str, str]] = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/pdf": "pdf",
        # A Zip container, because the signature cannot tell an .docx from an
        # .xlsx. The stored file name keeps the real one; this only decides
        # what the object key ends in.
        "application/zip": "zip",
    }
    MAGIC_SIGNATURES: ClassVar[Tuple[Tuple[bytes, str], ...]] = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"RIFF", "image/webp"),
    )
    CACHE_CONTROL: ClassVar[str] = "public, max-age=31536000, immutable"
    DOCUMENT_SIGNATURE: ClassVar[bytes] = b"%PDF-"
    DOCUMENT_CONTENT_TYPE: ClassVar[str] = "application/pdf"
    DOCUMENT_CACHE_CONTROL: ClassVar[str] = "private, no-store"
    #: What a team may share. Wider than the invoice sniffer because a team
    #: swaps rotas, protocols and photographs of a front door, and narrower
    #: than "anything" because these bytes are handed back to a browser.
    TEAM_DOCUMENT_SIGNATURES: ClassVar[Tuple[Tuple[bytes, str], ...]] = (
        (b"%PDF-", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        # Both an .docx and an .xlsx are Zip containers, so the signature
        # cannot tell them apart. The generic type is stored rather than a
        # guess: a browser downloads it either way, and a wrong specific
        # type would open the wrong application.
        (b"PK\x03\x04", "application/zip"),
    )

    def __init__(self, config: S3Config, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the storage without opening a connection.

        Args:
            config (S3Config): Bucket and credential settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            No client is built here. Constructing one resolves credentials,
            which would make importing this class fail on a machine that has
            none — including during a test collection that never uploads
            anything.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.client: Optional[BaseClient] = None
        self.logger.debug(
            "S3Storage created for bucket %s in %s.",
            self.config.bucket,
            self.config.region,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def get_client(self) -> BaseClient:
        """Return the boto3 S3 client, building it on first use.

        Returns:
            BaseClient: The configured client.

        Raises:
            MTS3BucketUnavailable: If credentials are missing or the client
                cannot be constructed.
        """
        if self.client is not None:
            return self.client
        try:
            self.client = boto3.client(
                "s3",
                region_name=self.config.region,
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.get_access_key(),
                aws_secret_access_key=self.config.get_secret_key(),
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        except Exception as exc:  # noqa: BLE001 - reported as unavailable
            self.logger.error(
                "Could not build the S3 client for bucket %s: %s.",
                self.config.bucket,
                exc,
            )
            raise MTS3BucketUnavailable(
                f"The object store for bucket {self.config.bucket!r} is not "
                f"available: {exc}."
            ) from exc
        self.logger.info("Built the S3 client for bucket %s.", self.config.bucket)
        return self.client

    def detect_content_type(self, payload: bytes) -> str:
        """Return the image type a payload actually is.

        Args:
            payload (bytes): The uploaded bytes.

        Returns:
            str: The detected content type.

        Raises:
            MTS3EmptyPayload: If ``payload`` carries no bytes.
            MTS3UnsupportedContentType: If the leading bytes match no accepted
                image format.

        Notes:
            WebP is checked with both its ``RIFF`` container marker and the
            ``WEBP`` tag at offset 8: ``RIFF`` alone also introduces WAV and
            AVI files, which would otherwise be accepted as images.
        """
        if not payload:
            self.logger.warning("Refused an empty upload.")
            raise MTS3EmptyPayload("The uploaded file is empty.")
        for signature, content_type in self.MAGIC_SIGNATURES:
            if not payload.startswith(signature):
                continue
            if content_type == "image/webp" and payload[8:12] != b"WEBP":
                continue
            self.logger.debug("Detected an upload of type %s.", content_type)
            return content_type
        self.logger.warning(
            "Refused an upload whose leading bytes match no accepted image type."
        )
        raise MTS3UnsupportedContentType(
            f"The uploaded file is not an accepted image. Must be one of: "
            f"{', '.join(sorted(self.CONTENT_TYPE_EXTENSIONS))}."
        )

    def build_logo_key(self, company_id: str, content_type: str) -> str:
        """Return the object key a company logo is written under.

        Args:
            company_id (str): The agency the logo belongs to.
            content_type (str): The detected image type.

        Returns:
            str: The key, under the configured logo prefix.

        Raises:
            MTS3UnsupportedContentType: If no extension is registered for the
                given content type.

        Notes:
            - Its own prefix, not a subfolder of the photographs. The two are
              removed by different rules — a logo outlives every assistant who
              ever worked for the agency — and sharing a prefix would make a
              bulk cleanup of one reach the other.
            - The extension is looked up rather than indexed, so an unmapped
              content type is reported as the refusal it is instead of a
              ``KeyError`` reaching the endpoint as an opaque 500.
        """
        self.logger.debug(
            "Building a logo key for company %s (%s).", company_id, content_type
        )
        extension = self.CONTENT_TYPE_EXTENSIONS.get(content_type)
        if extension is None:
            self.logger.error(
                "No file extension is registered for %s; the accepted types are %s.",
                content_type,
                ", ".join(sorted(self.CONTENT_TYPE_EXTENSIONS)),
            )
            raise MTS3UnsupportedContentType(
                f"The uploaded file is not an accepted image. Must be one of: "
                f"{', '.join(sorted(self.CONTENT_TYPE_EXTENSIONS))}."
            )
        if not company_id.strip():
            self.logger.warning(
                "Building a logo key for an unnamed company; the object would "
                "land directly under %s and no record could claim it.",
                self.config.logo_key_prefix,
            )
        key = f"{self.config.logo_key_prefix}{company_id}/{uuid4().hex}.{extension}"
        self.logger.info("Logo for company %s will be written to %s.", company_id, key)
        return key

    def build_photo_key(self, hca_id: str, content_type: str) -> str:
        """Return the object key a photograph is written under.

        Args:
            hca_id (str): The assistant the photograph belongs to.
            content_type (str): The detected image type.

        Returns:
            str: The key, under the configured photo prefix.

        Notes:
            A random component is appended so replacing a photograph writes a
            new key rather than overwriting the old one. Overwriting would
            leave every cached copy — browser, CDN — showing the previous
            image behind an unchanged URL.
        """
        extension = self.CONTENT_TYPE_EXTENSIONS[content_type]
        return f"{self.config.photo_key_prefix}{hca_id}/{uuid4().hex}.{extension}"  # noqa: E501

    async def upload_photo(self, hca_id: str, payload: bytes) -> str:
        """Store an assistant's photograph and return its URL.

        Args:
            hca_id (str): The assistant the photograph belongs to.
            payload (bytes): The image bytes.

        Returns:
            str: The URL the stored object is reachable at.

        Raises:
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If the upload is not an accepted image.
            MTS3PayloadTooLarge: If the upload exceeds the configured size.
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3UploadFailed: If the object could not be written.
        """
        if len(payload) > self.config.max_upload_bytes:
            self.logger.warning(
                "Refused a %d-byte upload for hca %s; the limit is %d.",
                len(payload),
                hca_id,
                self.config.max_upload_bytes,
            )
            raise MTS3PayloadTooLarge(
                f"The uploaded file is {len(payload)} bytes; the limit is "
                f"{self.config.max_upload_bytes}."
            )
        content_type = self.detect_content_type(payload)
        key = self.build_photo_key(hca_id, content_type)
        client = self.get_client()
        self.logger.info(
            "Uploading a %d-byte %s photograph for hca %s to %s.",
            len(payload),
            content_type,
            hca_id,
            key,
        )
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self.config.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                CacheControl=self.CACHE_CONTROL,
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error(
                "Failed to upload the photograph for hca %s: %s.", hca_id, exc
            )
            raise MTS3UploadFailed(f"Could not store the photograph: {exc}.") from exc  # noqa: E501
        url = self.config.build_public_url(key)
        self.logger.info("Stored the photograph for hca %s at %s.", hca_id, url)  # noqa: E501
        return url

    async def upload_logo(self, company_id: str, payload: bytes) -> str:
        """Store an agency's logo and return its URL.

        Args:
            company_id (str): The agency the logo belongs to.
            payload (bytes): The image bytes.

        Returns:
            str: The URL the stored object is reachable at.

        Raises:
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If the upload is not an accepted image.
            MTS3PayloadTooLarge: If the upload exceeds the configured size.
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            The same checks as a photograph, deliberately: the size limit and
            the accepted formats are a property of *this bucket serving these
            images to a browser*, not of whose face is in them.
        """
        if len(payload) > self.config.max_upload_bytes:
            self.logger.warning(
                "Refused a %d-byte logo for company %s; the limit is %d.",
                len(payload),
                company_id,
                self.config.max_upload_bytes,
            )
            raise MTS3PayloadTooLarge(
                f"The uploaded file is {len(payload)} bytes; the limit is "
                f"{self.config.max_upload_bytes}."
            )
        self.logger.debug(
            "Accepted a %d-byte logo for company %s; detecting its type.",
            len(payload),
            company_id,
        )
        content_type = self.detect_content_type(payload)
        key = self.build_logo_key(company_id, content_type)
        client = self.get_client()
        self.logger.info(
            "Uploading a %d-byte %s logo for company %s to %s.",
            len(payload),
            content_type,
            company_id,
            key,
        )
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self.config.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                CacheControl=self.CACHE_CONTROL,
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error(
                "Failed to upload the logo for company %s: %s.",
                company_id,
                exc,  # noqa: E501
            )
            raise MTS3UploadFailed(f"Could not store the logo: {exc}.") from exc  # noqa: E501
        url = self.config.build_public_url(key)
        self.logger.info("Stored the logo for company %s at %s.", company_id, url)  # noqa: E501
        return url

    async def delete_logo(self, logo_url: str) -> bool:
        """Remove a stored company logo.

        Args:
            logo_url (str): The URL the logo is reachable at.

        Returns:
            bool: ``True`` when the object was removed, ``False`` when the URL
            does not belong to this bucket's logo prefix.

        Raises:
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3DeleteFailed: If the object could not be removed.
        """
        key = self.key_for_url(logo_url, prefix=self.config.logo_key_prefix)
        if key is None:
            self.logger.warning(
                "Refused to delete %s: it is not a logo in this bucket.",
                logo_url,  # noqa: E501
            )
            return False
        client = self.get_client()
        self.logger.info("Deleting the logo at %s.", key)
        try:
            await asyncio.to_thread(
                client.delete_object, Bucket=self.config.bucket, Key=key
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error("Failed to delete the logo %s: %s.", key, exc)
            raise MTS3DeleteFailed(f"Could not remove the logo: {exc}.") from exc  # noqa: E501
        self.logger.debug("Deleted the logo at %s.", key)
        return True

    async def fetch_logo(self, logo_url: str) -> Optional[bytes]:
        """Read a stored logo back, for a document that has to embed it.

        Args:
            logo_url (str): The URL the logo is reachable at.

        Returns:
            Optional[bytes]: The image bytes, or ``None`` when the URL is not a
            logo in this bucket or the object could not be read.

        Notes:
            **Reports rather than raises**, unlike every write here. The one
            caller is the quote renderer, and a quote that could not be sent
            because a decoration was missing would be a worse outcome than one
            that goes out without its letterhead.
        """
        key = self.key_for_url(logo_url, prefix=self.config.logo_key_prefix)
        if key is None:
            self.logger.warning(
                "Refused to fetch %s: it is not a logo in this bucket.",
                logo_url,  # noqa: E501
            )
            return None
        self.logger.debug("Fetching the logo at %s.", key)
        try:
            client = self.get_client()
            response = await asyncio.to_thread(
                client.get_object, Bucket=self.config.bucket, Key=key
            )
            payload = await asyncio.to_thread(response["Body"].read)
        except (BotoCoreError, ClientError, MTS3BucketUnavailable, KeyError) as exc:  # noqa: E501
            self.logger.error(
                "Could not read the logo %s: %s. The document that wanted it "
                "will be produced without one.",
                key,
                exc,
            )
            return None
        if not payload:
            self.logger.warning(
                "The logo at %s is a zero-byte object; treating it as absent.", key
            )
            return None
        self.logger.info("Read %d bytes of logo from %s.", len(payload), key)
        return payload

    def detect_document_type(self, payload: bytes) -> str:
        """Return the document type a payload actually is.

        Args:
            payload (bytes): The rendered document bytes.

        Returns:
            str: ``"application/pdf"``.

        Raises:
            MTS3EmptyPayload: If ``payload`` carries no bytes.
            MTS3UnsupportedContentType: If the leading bytes are not a PDF's.

        Notes:
            - **A parallel sniffer, deliberately not a relaxation of
              :meth:`detect_content_type`.** That one guards a bucket serving
              images to a browser, and widening its allow-list to admit a document
              would admit it for photographs and logos too — which is exactly how
              a stored file becomes a stored payload. Invoices get their own
              check, their own prefix and their own cache headers.
            - Checked at all even though this application generated the bytes
              itself: the check costs five bytes of comparison and catches a
              renderer that returned an error page, which would otherwise be
              stored under a legal invoice number and emailed to a customer.
        """
        if not payload:
            self.logger.warning("Refused an empty document.")
            raise MTS3EmptyPayload("The document is empty.")
        if not payload.startswith(self.DOCUMENT_SIGNATURE):
            self.logger.warning(
                "Refused a document whose leading bytes are not a PDF's."
            )
            raise MTS3UnsupportedContentType(
                "The document is not a PDF. Only "
                f"{self.DOCUMENT_CONTENT_TYPE} is stored under the invoice "
                "prefix."
            )
        self.logger.debug("Detected a document of type %s.", self.DOCUMENT_CONTENT_TYPE)  # noqa: E501
        return self.DOCUMENT_CONTENT_TYPE

    def build_invoice_key(self, company_id: str, number: str) -> str:
        """Return the object key an invoice document is written under.

        Args:
            company_id (str): The agency that issued the invoice.
            number (str): The invoice number, used only for the log.

        Returns:
            str: The key, under the configured invoice prefix.

        Notes:
            **The key is random, not derived from the invoice number.** The
            number is printed on a document a customer holds, so a key built
            from it would be guessable by anybody who has ever received one —
            and these objects are the agency's whole billing history. The number
            stays the human-facing identity; the key stays unguessable.
        """
        if not company_id.strip():
            self.logger.warning(
                "Building an invoice key for an unnamed company; the object "
                "would land directly under %s and no record could claim it.",
                self.config.invoice_key_prefix,
            )
        key = f"{self.config.invoice_key_prefix}{company_id}/{uuid4().hex}.pdf"
        self.logger.info("Invoice %s will be written to %s.", number, key)
        return key

    async def upload_invoice(self, company_id: str, number: str, payload: bytes) -> str:
        """Store an invoice document and return its object key.

        Args:
            company_id (str): The agency that issued the invoice.
            number (str): The invoice number, used for the log and the key.
            payload (bytes): The rendered PDF.

        Returns:
            str: The **object key**, not a URL.

        Raises:
            MTS3EmptyPayload: If the document carries no bytes.
            MTS3UnsupportedContentType: If the document is not a PDF.
            MTS3PayloadTooLarge: If the document exceeds the configured size.
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            - **Returns a key and never a URL**, unlike the photograph and logo
              paths. Those objects are fetched by a browser; an invoice is only
              ever read back server-side and streamed through an authenticated
              endpoint, so there is no public URL to build and storing one would
              invite somebody to use it.
            - Written with ``private, no-store`` rather than the year-long
              immutable cache the images carry. A financial document sitting in
              an intermediary cache is the same exposure by another route.
        """
        if len(payload) > self.config.max_upload_bytes:
            self.logger.warning(
                "Refused a %d-byte invoice document for %s; the limit is %d.",
                len(payload),
                number,
                self.config.max_upload_bytes,
            )
            raise MTS3PayloadTooLarge(
                f"The document is {len(payload)} bytes; the limit is "
                f"{self.config.max_upload_bytes}."
            )
        content_type = self.detect_document_type(payload)
        key = self.build_invoice_key(company_id, number)
        client = self.get_client()
        self.logger.info(
            "Uploading a %d-byte document for invoice %s to %s.",
            len(payload),
            number,
            key,
        )
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self.config.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                CacheControl=self.DOCUMENT_CACHE_CONTROL,
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error(
                "Failed to upload the document for invoice %s: %s.", number, exc
            )
            raise MTS3UploadFailed(
                f"Could not store the invoice document: {exc}."
            ) from exc
        self.logger.info("Stored the document for invoice %s at %s.", number, key)
        return key

    async def fetch_invoice(self, document_key: str) -> Optional[bytes]:
        """Read a stored invoice document back.

        Args:
            document_key (str): The object key the document was written under.

        Returns:
            Optional[bytes]: The PDF bytes, or ``None`` when the key is not an
            invoice in this bucket or the object could not be read.

        Notes:
            - Takes a **key**, not a URL, because that is what
              :meth:`upload_invoice` returns and what the bill stores. The
              prefix is still checked: a key arriving from anywhere else must
              not be able to read an assistant's photograph out of the same
              bucket.
            - Reports rather than raises, like :meth:`fetch_logo`, so the
              download endpoint answers a clean "the document is unavailable"
              instead of a stack trace.
        """
        if not isinstance(document_key, str) or not document_key.strip():
            self.logger.warning("Cannot fetch an invoice without a key.")
            return None
        key = document_key.strip()
        if not key.startswith(self.config.invoice_key_prefix):
            self.logger.warning(
                "Refused to fetch %r: it is not under %s.",
                key,
                self.config.invoice_key_prefix,
            )
            return None
        self.logger.debug("Fetching the invoice document at %s.", key)
        try:
            client = self.get_client()
            response = await asyncio.to_thread(
                client.get_object, Bucket=self.config.bucket, Key=key
            )
            payload = await asyncio.to_thread(response["Body"].read)
        except (BotoCoreError, ClientError, MTS3BucketUnavailable, KeyError) as exc:  # noqa: E501
            self.logger.error("Could not read the invoice document %s: %s.", key, exc)
            return None
        if not payload:
            self.logger.warning(
                "The invoice document at %s is a zero-byte object; treating it "
                "as absent.",
                key,
            )
            return None
        self.logger.info("Read %d bytes of invoice from %s.", len(payload), key)  # noqa: E501
        return payload

    async def delete_invoice(self, document_key: str) -> bool:
        """Remove a stored invoice document.

        Args:
            document_key (str): The object key the document was written under.

        Returns:
            bool: ``True`` when the object was removed.

        Notes:
            Exists for the superseded document a re-render leaves behind, not
            for withdrawing an invoice: a number taken out of the series is the
            gap French invoicing forbids, and the record itself is never
            deleted. The prefix check is what stops a stray key reaching a
            photograph.
        """
        if not isinstance(document_key, str) or not document_key.strip():
            self.logger.warning("Cannot delete an invoice without a key.")
            return False
        key = document_key.strip()
        if not key.startswith(self.config.invoice_key_prefix):
            self.logger.warning(
                "Refused to delete %r: it is not under %s.",
                key,
                self.config.invoice_key_prefix,
            )
            return False
        self.logger.info("Deleting the invoice document at %s.", key)
        try:
            client = self.get_client()
            await asyncio.to_thread(
                client.delete_object, Bucket=self.config.bucket, Key=key
            )
        except (BotoCoreError, ClientError, MTS3BucketUnavailable) as exc:
            self.logger.error("Could not delete the invoice document %s: %s.", key, exc)
            return False
        self.logger.debug("Deleted the invoice document at %s.", key)
        return True

    def detect_team_document_type(self, payload: bytes) -> str:
        """Return the media type a team document actually is.

        Args:
            payload (bytes): The uploaded bytes.

        Returns:
            str: The detected media type.

        Raises:
            MTS3EmptyPayload: If ``payload`` carries no bytes.
            MTS3UnsupportedContentType: If the leading bytes match nothing in
                :attr:`TEAM_DOCUMENT_SIGNATURES`.

        Notes:
            - **A third sniffer, and deliberately not a widening of either
              existing one.** :meth:`detect_content_type` guards a bucket
              serving portraits to a browser and :meth:`detect_document_type`
              exists to prove a payload is an invoice; admitting a spreadsheet
              to either would admit it for photographs or for legal documents
              too. A team's shared space gets its own allow-list, its own prefix
              and the private cache header.
            - Detected from **magic bytes, never the declared ``Content-Type``**,
              which is a claim by whoever uploaded the file. The stored value is
              what a download hands back, so trusting the header would let an
              uploader choose how a colleague's browser treats their bytes.
        """
        if not payload:
            self.logger.warning("Refused an empty team document.")
            raise MTS3EmptyPayload("The document is empty.")
        for signature, content_type in self.TEAM_DOCUMENT_SIGNATURES:
            if payload.startswith(signature):
                self.logger.debug("Detected a team document of type %s.", content_type)
                return content_type
        accepted = ", ".join(
            content_type for _, content_type in self.TEAM_DOCUMENT_SIGNATURES
        )
        self.logger.warning("Refused a team document of an unrecognised type.")
        raise MTS3UnsupportedContentType(
            f"That file type cannot be shared. Accepted types are {accepted}."
        )

    def build_team_document_key(self, team_id: str, content_type: str) -> str:
        """Return the object key a team document is written under.

        Args:
            team_id (str): The team whose space the file joins.
            content_type (str): The detected media type, for the extension.

        Returns:
            str: The key, under the configured team-document prefix.

        Notes:
            **The key is random, not derived from the file name.** A key built
            from what somebody called their file would be guessable by anybody
            who has seen the name, and these objects are a team's private
            paperwork. The file name stays the human-facing identity, stored on
            the row; the key stays unguessable.
        """
        if not team_id.strip():
            self.logger.warning(
                "Building a team-document key for an unnamed team; the object "
                "would land directly under %s and no record could claim it.",
                self.config.team_document_key_prefix,
            )
        extension = self.CONTENT_TYPE_EXTENSIONS.get(content_type, "bin")
        key = (
            f"{self.config.team_document_key_prefix}{team_id}/{uuid4().hex}.{extension}"
        )
        self.logger.info("A document for team %s will be written to %s.", team_id, key)
        return key

    async def upload_team_document(
        self, team_id: str, payload: bytes
    ) -> Tuple[str, str]:
        """Store a shared team document and return its key and type.

        Args:
            team_id (str): The team whose space the file joins.
            payload (bytes): The uploaded bytes.

        Returns:
            Tuple[str, str]: The **object key** and the detected media type.

        Raises:
            MTS3EmptyPayload: If the file carries no bytes.
            MTS3UnsupportedContentType: If the file is not a shareable type.
            MTS3PayloadTooLarge: If the file exceeds the configured size.
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            - **Returns a key and never a URL**, like the invoice path and
              unlike the portrait one. A team's documents are read back
              server-side and streamed through an authenticated endpoint, so
              there is no public URL to build and storing one would invite
              somebody to use it.
            - The detected type comes back with the key because the caller has
              to store it: it is what the download hands to a browser, and
              re-sniffing the object on every read would mean fetching it twice.
        """
        if len(payload) > self.config.max_upload_bytes:
            self.logger.warning(
                "Refused a %d-byte document for team %s; the limit is %d.",
                len(payload),
                team_id,
                self.config.max_upload_bytes,
            )
            raise MTS3PayloadTooLarge(
                f"The file is {len(payload)} bytes; the limit is "
                f"{self.config.max_upload_bytes}."
            )
        content_type = self.detect_team_document_type(payload)
        key = self.build_team_document_key(team_id, content_type)
        client = self.get_client()
        self.logger.info(
            "Uploading a %d-byte %s document for team %s to %s.",
            len(payload),
            content_type,
            team_id,
            key,
        )
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self.config.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                CacheControl=self.DOCUMENT_CACHE_CONTROL,
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error(
                "Failed to upload a document for team %s: %s.", team_id, exc
            )
            raise MTS3UploadFailed(
                f"Could not store the shared document: {exc}."
            ) from exc
        self.logger.info("Stored a document for team %s at %s.", team_id, key)
        return key, content_type

    async def fetch_team_document(self, document_key: str) -> Optional[bytes]:
        """Read a stored team document back.

        Args:
            document_key (str): The object key the file was written under.

        Returns:
            Optional[bytes]: The bytes, or ``None`` when the key is not a team
            document in this bucket or the object could not be read.

        Notes:
            The prefix is re-checked here rather than trusted from the row. The
            key reaches this method from a stored record, and a record pointing
            outside the team-document prefix would let an authenticated download
            address any object in the bucket — the invoices among them.
        """
        key = document_key.strip()
        if not key.startswith(self.config.team_document_key_prefix):
            self.logger.warning(
                "Refused to read %s: it does not lie under %s.",
                key,
                self.config.team_document_key_prefix,
            )
            return None
        client = self.get_client()
        self.logger.debug("Reading the team document at %s.", key)
        try:
            response = await asyncio.to_thread(
                client.get_object, Bucket=self.config.bucket, Key=key
            )
            payload = response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            self.logger.error("Failed to read the team document %s: %s.", key, exc)
            return None
        self.logger.info(
            "Read %d byte(s) from the team document %s.", len(payload), key
        )
        return payload

    async def delete_team_document(self, document_key: str) -> bool:
        """Remove a stored team document.

        Args:
            document_key (str): The object key the file was written under.

        Returns:
            bool: ``True`` when the object was removed.

        Notes:
            The same prefix check as the read, and for the stronger reason:
            getting it wrong here removes somebody else's object rather than
            merely reading one.
        """
        key = document_key.strip()
        if not key.startswith(self.config.team_document_key_prefix):
            self.logger.warning(
                "Refused to delete %s: it does not lie under %s.",
                key,
                self.config.team_document_key_prefix,
            )
            return False
        client = self.get_client()
        self.logger.info("Deleting the team document at %s.", key)
        try:
            await asyncio.to_thread(
                client.delete_object, Bucket=self.config.bucket, Key=key
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error("Failed to delete the team document %s: %s.", key, exc)
            return False
        self.logger.info("Deleted the team document at %s.", key)
        return True

    async def delete_photo(self, photo_url: str) -> bool:
        """Remove a stored photograph.

        Args:
            photo_url (str): The URL the photograph is reachable at.

        Returns:
            bool: ``True`` when the object was removed, ``False`` when the URL
            does not belong to this bucket.

        Raises:
            MTS3BucketUnavailable: If the client cannot be built.
            MTS3DeleteFailed: If the object could not be removed.

        Notes:
            A URL that does not resolve to a key under the configured photo
            prefix is refused rather than deleted. Without that check, passing
            an arbitrary URL would let a caller delete any object in the
            bucket.
        """
        key = self.key_for_url(photo_url)
        if key is None:
            self.logger.warning(
                "Refused to delete %s: it is not a photograph in this bucket.",
                photo_url,
            )
            return False
        client = self.get_client()
        self.logger.info("Deleting the photograph at %s.", key)
        try:
            await asyncio.to_thread(
                client.delete_object, Bucket=self.config.bucket, Key=key
            )
        except (BotoCoreError, ClientError) as exc:
            self.logger.error("Failed to delete the photograph %s: %s.", key, exc)  # noqa: E501
            raise MTS3DeleteFailed(f"Could not remove the photograph: {exc}.") from exc  # noqa: E501
        self.logger.debug("Deleted the photograph at %s.", key)
        return True

    def key_for_url(
        self, object_url: str, prefix: Optional[str] = None
    ) -> Optional[str]:
        """Return the object key a stored-image URL points at.

        Args:
            object_url (str): The URL to resolve.
            prefix (Optional[str]): The key prefix the object must lie under.
                Defaults to the photo prefix, which is what the existing
                callers mean.

        Returns:
            Optional[str]: The key, or ``None`` when the URL is not an object
            stored by this configuration under that prefix.

        Notes:
            - The path is matched against the prefix after the bucket segment is
              stripped, so both the virtual-host and path-style URL forms resolve
              to the same key.
            - One resolver for both prefixes rather than one per kind of image.
              This is the check that stops an arbitrary URL being turned into a
              delete of somebody else's object, and two copies of it are two
              chances for one of them to be relaxed.
        """
        expected = prefix if prefix else self.config.photo_key_prefix
        self.logger.debug("Resolving %r against the %s prefix.", object_url, expected)  # noqa: E501
        if not isinstance(object_url, str) or not object_url.strip():
            self.logger.warning(
                "Cannot resolve an empty URL; nothing will be acted on."
            )
            return None
        try:
            path = urlparse(object_url.strip()).path.lstrip("/")
        except ValueError as exc:
            self.logger.error("Could not parse %r as a URL: %s.", object_url, exc)  # noqa: E501
            return None
        if not path:
            self.logger.warning("The URL %r names no object path.", object_url)
            return None
        bucket_segment = f"{self.config.bucket}/"
        path = path.removeprefix(bucket_segment)
        if not path.startswith(expected):
            self.logger.warning(
                "The URL %r resolves to %r, which is not under %s; refusing it.",  # noqa: E501
                object_url,
                path,
                expected,
            )
            return None
        self.logger.info("Resolved %r to the object key %s.", object_url, path)
        return path

    async def ensure_bucket(self) -> bool:
        """Verify the configured bucket is reachable.

        Returns:
            bool: ``True`` when the bucket answered.

        Notes:
            Reports rather than raises, so a start-up check can log a warning
            and carry on. Photographs are optional, and refusing to serve the
            whole API because the object store is down would take the planning
            with it.
        """
        try:
            client = self.get_client()
            await asyncio.to_thread(client.head_bucket, Bucket=self.config.bucket)  # noqa: E501
        except (BotoCoreError, ClientError, MTS3BucketUnavailable) as exc:
            self.logger.warning(
                "Bucket %s is not reachable: %s.", self.config.bucket, exc
            )
            return False
        self.logger.info("Bucket %s is reachable.", self.config.bucket)
        return True
