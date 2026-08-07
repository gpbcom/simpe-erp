from __future__ import annotations

# Standard library imports
import secrets  # isort: skip
from datetime import UTC, datetime, timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple, Union

# Third-party imports
# isort: off
import bcrypt
from jose import JWTError, jwt

# isort: on
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.auth.access_token import AccessToken
from models.auth.user import User
from models.configuration.auth_config import AuthConfig
from models.configuration.exceptions import MTAuthConfigMissingSecret
from models.enums import AccountOrigin, Language, UserRole
from service.auth.exceptions import (
    MTAuthCompanyRequired,
    MTAuthEmailAlreadyRegistered,
    MTAuthHcaLinkRequired,
    MTAuthInvalidCredentials,
    MTAuthInvalidToken,
    MTAuthLastAdmin,
    MTAuthMissingSecret,
    MTAuthPasswordChangeRequired,
    MTAuthSamePassword,
    MTAuthUnknownAccount,
    MTAuthUnknownHca,
    MTAuthUserInactive,
)
from storage.repositories.people.hca import HcaRepository
from storage.repositories.auth.user import UserRepository
from storage.s3.exceptions import MTS3DeleteFailed
from storage.s3.s3_storage import S3Storage


class AuthService:
    """Registers accounts, authenticates sign-ins and resolves tokens.

    Attributes:
        users (UserRepository): The account store.
        hcas (HcaRepository): The assistant store, used to validate the link.
        photos (Optional[S3Storage]): The object store holding the portraits,
            needed only by the portrait methods.
        hasher (PasswordHasher): Hashes and verifies passwords.
        issuer (TokenIssuer): Mints and reads access tokens.
        logger (Logger): Logger for authentication operations.

    Notes:
        Every sign-in failure raises the same exception with the same message,
        whether the address is unknown or the password is wrong. Telling the
        two apart would turn the endpoint into an account-enumeration oracle.
        A deactivated account is the one exception: it is a distinct answer
        because the person needs to know to contact an administrator, and the
        caller has already proved they hold the password.
    """

    DUMMY_HASH: ClassVar[str] = (
        "$2b$12$bnQK43L5aiDh9kRY3zCCgeVSO0h0rGGyWjHBxlnBVeCFRSZAftegK"
    )

    MAX_PASSWORD_BYTES: ClassVar[int] = 72
    SUBJECT_CLAIM: ClassVar[str] = "sub"
    ISSUED_AT_CLAIM: ClassVar[str] = "iat"
    EXPIRY_CLAIM: ClassVar[str] = "exp"
    SCOPE_CLAIM: ClassVar[str] = "scope"
    STREAM_SCOPE: ClassVar[str] = "stream"
    STREAM_TOKEN_TTL_SECONDS: ClassVar[int] = 60
    TEMPORARY_PASSWORD_ALPHABET: ClassVar[str] = (
        "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*-_=+"
    )
    TEMPORARY_PASSWORD_LENGTH: ClassVar[int] = 16

    def __init__(
        self,
        users: UserRepository,
        hcas: HcaRepository,
        config: AuthConfig,
        photos: Optional[S3Storage] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            users (UserRepository): The account store.
            hcas (HcaRepository): The assistant store.
            config (AuthConfig): The signing settings tokens are minted with.
            photos (Optional[S3Storage]): The object store holding the
                portraits, needed only by :meth:`set_photo` and
                :meth:`clear_photo`.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.users = users
        self.hcas = hcas
        self.config = config
        self.photos = photos
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("AuthService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _remove_superseded(
        self, previous_url: Optional[str], current_url: Optional[str]
    ) -> None:
        """Delete a portrait that is no longer referenced, best effort.

        Args:
            previous_url (Optional[str]): The URL stored before.
            current_url (Optional[str]): The URL stored now, so an unchanged
                one is never deleted.

        Notes:
            Failures are logged, never raised. By the time this runs the account
            is already correct, so raising would report a failure for an
            operation that succeeded. The cost is an orphaned object, which is a
            housekeeping problem rather than a correctness one.
        """
        if not previous_url or previous_url == current_url:
            return
        try:
            await self.photos.delete_photo(previous_url)
        except MTS3DeleteFailed as exc:
            self.logger.warning(
                "Could not remove the superseded portrait %s: %s. The object is "
                "orphaned but the account is correct.",
                previous_url,
                exc,
            )

    def _stored_id(self, user: User) -> str:
        """Return the identifier a stored account must carry.

        Args:
            user (User): The account taken from the credential.

        Returns:
            str: The account's identifier.

        Raises:
            MTAuthUnknownAccount: If the account carries none.

        Notes:
            An account resolved from a bearer token was read back from the
            store, so it always has one. The check is here because the field is
            optional on the model — it has to be, since an account is built
            before it is inserted — and a ``None`` reaching the object key would
            write every such portrait under the same prefix.
        """
        if not user.id:
            self.logger.error(
                "Account %s carries no identifier; it cannot own a portrait.",
                user.email,
            )
            raise MTAuthUnknownAccount("The account has not been stored yet.")
        return user.id

    async def _mirror_to_assistant(self, user: User, photo_url: Optional[str]) -> None:  # noqa: E501
        """Point the caller's assistant record at the same portrait.

        Args:
            user (User): The account whose portrait changed.
            photo_url (Optional[str]): The URL now stored, or ``None``.

        Notes:
            - An assistant's portrait **is their pin on the manager's map**, and
              it is the same photograph of the same person. Writing only the
              account would leave somebody who has just uploaded a face still
              showing as initials on the map — which reads as the upload not
              having worked.
            - An account bound to no assistant record skips this entirely, which
              is every manager and administrator.
        """
        if not user.hca_id:
            self.logger.debug(
                "Account %s is bound to no assistant record; its portrait is "
                "not mirrored.",
                user.id,
            )
            return
        if await self.hcas.set_photo_url(user.hca_id, photo_url) is None:
            self.logger.error(
                "Account %s names assistant %s, which does not exist; the map "
                "pin still shows the previous portrait.",
                user.id,
                user.hca_id,
            )
            return
        self.logger.info(
            "Assistant %s now shows the portrait of account %s.",
            user.hca_id,
            user.id,
        )

    def _decode(self, token: str) -> Dict[str, Union[str, int]]:
        """Verify a token's signature and expiry, and return its claims.

        Args:
            token (str): The token to decode.

        Returns:
            Dict[str, Union[str, int]]: The verified claims.

        Raises:
            MTAuthMissingSecret: If the signing secret is not configured.
            MTAuthInvalidToken: If the token is malformed, expired or signed
                with the wrong key.

        Notes:
            Only the configured algorithm is accepted. Passing the whole
            supported set would let a token nominate its own algorithm, which
            is the ``alg`` confusion attack.
        """
        try:
            secret = self.config.get_jwt_secret()
        except MTAuthConfigMissingSecret as exc:
            self.logger.error("Cannot decode a token: %s.", exc)
            raise MTAuthMissingSecret(str(exc)) from exc
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[self.config.jwt_algorithm],
            )
        except JWTError as exc:
            self.logger.warning("Rejected a token: %s.", exc)
            raise MTAuthInvalidToken("The access token is not valid.") from exc

    ############################
    # Publicly Exposed Methods #
    ############################

    async def set_photo(self, user: User, payload: bytes) -> User:
        """Store the caller's portrait and attach it to their account.

        Args:
            user (User): The account the portrait belongs to, taken from the
                credential.
            payload (bytes): The image bytes.

        Returns:
            User: The updated account.

        Raises:
            MTAuthUnknownAccount: If the account vanished mid-write.
            MTS3EmptyPayload: If the upload carries no bytes.
            MTS3UnsupportedContentType: If it is not an accepted image.
            MTS3PayloadTooLarge: If it exceeds the configured size.
            MTS3BucketUnavailable: If the object store cannot be reached.
            MTS3UploadFailed: If the object could not be written.

        Notes:
            - **The account comes from the credential, never from a parameter.**
              There is no ``user_id`` to pass, so the only portrait a caller can
              replace is their own — the same shape :meth:`update_account` uses.
            - The object is written **before** the account is updated. The
              reverse order would leave a row pointing at an object that does
              not exist yet, so a failure between the two steps would show a
              broken image rather than the previous one.
            - A photograph is uploaded as a **file**, never as a URL. Accepting
              a URL would let somebody point their avatar at any address on the
              internet, which every screen would then load.
        """
        account_id = self._stored_id(user)
        previous_url = str(user.photo_url) if user.photo_url is not None else None
        self.logger.info(
            "Storing a %d-byte portrait for account %s.",
            len(payload),
            account_id,
        )
        photo_url = await self.photos.upload_photo(account_id, payload)
        updated = await self.users.set_photo_url(account_id, photo_url)
        if updated is None:
            self.logger.error(
                "Account %s vanished while its portrait was uploading; the "
                "object at %s is now orphaned.",
                account_id,
                photo_url,
            )
            raise MTAuthUnknownAccount("The account no longer exists.")
        await self._mirror_to_assistant(updated, photo_url)
        await self._remove_superseded(previous_url, photo_url)
        self.logger.info("Account %s now shows %s.", account_id, photo_url)
        return updated

    async def clear_photo(self, user: User) -> User:
        """Remove the caller's portrait.

        Args:
            user (User): The account to clear, taken from the credential.

        Returns:
            User: The updated account, with no portrait.

        Raises:
            MTAuthUnknownAccount: If the account vanished mid-write.

        Notes:
            - The link is cleared first, the opposite of the upload order. What
              matters in both cases is that the row never points at a missing
              object: on upload the object must exist first, on removal the link
              must go first.
            - Every screen falls back to the holder's initials, so removing a
              portrait leaves a legible avatar rather than a blank circle.
        """
        account_id = self._stored_id(user)
        previous_url = str(user.photo_url) if user.photo_url is not None else None
        updated = await self.users.set_photo_url(account_id, None)
        if updated is None:
            self.logger.error(
                "Account %s vanished between the read and the portrait write.",
                account_id,
            )
            raise MTAuthUnknownAccount("The account no longer exists.")
        await self._mirror_to_assistant(updated, None)
        await self._remove_superseded(previous_url, None)
        self.logger.info("Account %s no longer has a portrait.", account_id)
        return updated

    async def register(
        self,
        email: str,
        full_name: str,
        password: str,
        role: UserRole = UserRole.HCA,
        hca_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> User:
        """Create an account.

        Args:
            email (str): The sign-in address.
            full_name (str): The display name.
            password (str): The plaintext password.
            role (UserRole): The role to grant.
            hca_id (Optional[str]): The assistant record to link, required for
                an assistant account.
            company_id (Optional[str]): The agency the account belongs to.

        Returns:
            User: The stored account.

        Raises:
            MTAuthCompanyRequired: If no agency was resolved for the account.
            MTAuthHcaLinkRequired: If an assistant account names no record.
            MTAuthUnknownHca: If the named assistant record does not exist.
            MTAuthEmailAlreadyRegistered: If the address is already in use.

        Notes:
            The assistant link is checked here rather than left to the foreign
            key: a database error would surface as a 500, while this reports a
            precise 4xx naming what is wrong.
        """
        self.logger.info("Registering %s with role %s.", email, role.value)
        if role is UserRole.HCA:
            if not hca_id:
                self.logger.warning(
                    "Refused to register %s: an assistant account needs a record.",
                    email,
                )
                raise MTAuthHcaLinkRequired(
                    "An account with the 'hca' role must name the assistant "
                    "record it belongs to."
                )
            assistant = await self.hcas.get(hca_id)
            if assistant is None:
                self.logger.warning(
                    "Refused to register %s: unknown assistant %s.",
                    email,
                    hca_id,
                )
                raise MTAuthUnknownHca(f"No assistant record {hca_id!r} exists.")
            company_id = assistant.company_id
        if not company_id:
            self.logger.warning(
                "Refused to register %s: no agency was resolved for the account.",
                email,
            )
            raise MTAuthCompanyRequired(
                f"An account must belong to an agency; none was resolved for {email!r}."
            )
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=self.hash(password),
            role=role,
            hca_id=hca_id,
            company_id=company_id,
        )
        try:
            stored = await self.users.create(user)
        except IntegrityError as exc:
            self.logger.warning("Address %s is already registered.", email)
            raise MTAuthEmailAlreadyRegistered(
                f"An account is already registered under {email!r}."
            ) from exc
        self.logger.info("Registered account %s.", stored.id)
        return stored

    async def create_staff_account(
        self,
        email: str,
        full_name: str,
        hca_id: str,
        company_id: Optional[str] = None,
    ) -> Tuple[User, str]:
        """Create an assistant's account on their behalf, with a one-time password.

        Args:
            email (str): The sign-in address.
            full_name (str): The display name.
            hca_id (str): The assistant record the account belongs to.
            company_id (Optional[str]): The company they work for.

        Returns:
            Tuple[User, str]: The stored account, and the temporary password in
            plain text — returned **once**, for the administrator to hand over.

        Raises:
            MTAuthCompanyRequired: If no agency was resolved for the account.
            MTAuthUnknownHca: If the named assistant record does not exist.
            MTAuthEmailAlreadyRegistered: If the address is already in use.

        Notes:
            - This is the second of the two ways an assistant account comes to
              exist: an administrator or manager creates it, and the assistant
              changes the password at their first sign-in.
            - The plaintext is returned rather than stored or emailed. It exists
              in this process for as long as it takes to build the response, and
              after that only its hash exists anywhere — so an administrator who
              loses it regenerates rather than looks it up, which is the correct
              trade.
            - ``must_change_password`` is set here, but the account model refuses
              to be built without it for a staff-created origin. Two gates,
              because the one that matters is the one nobody has to remember.
        """
        self.logger.info(
            "Creating a staff-issued account for %s (assistant %s).",
            email,
            hca_id,
        )
        assistant = await self.hcas.get(hca_id)
        if assistant is None:
            self.logger.warning(
                "Refused to create an account for %s: unknown assistant %s.",
                email,
                hca_id,
            )
            raise MTAuthUnknownHca(f"No assistant record {hca_id!r} exists.")

        company_id = assistant.company_id or company_id
        if not company_id:
            self.logger.warning(
                "Refused to create an account for %s: no agency was resolved.",
                email,
            )
            raise MTAuthCompanyRequired(
                f"An account must belong to an agency; none was resolved for {email!r}."
            )

        temporary_password = self.generate_temporary_password()
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=self.hash(temporary_password),
            role=UserRole.HCA,
            hca_id=hca_id,
            company_id=company_id,
            account_origin=AccountOrigin.CREATED_BY_STAFF,
            must_change_password=True,
        )
        try:
            stored = await self.users.create(user)
        except IntegrityError as exc:
            self.logger.warning("Address %s is already registered.", email)
            raise MTAuthEmailAlreadyRegistered(
                f"An account is already registered under {email!r}."
            ) from exc
        self.logger.warning(
            "Account %s was created with a temporary password and cannot be "
            "used until it is changed.",
            stored.id,
        )
        return stored, temporary_password

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> User:
        """Replace an account's password, clearing any forced-change flag.

        Args:
            user (User): The account changing its password.
            current_password (str): The password being replaced.
            new_password (str): The password to set.

        Returns:
            User: The updated account.

        Raises:
            MTAuthInvalidCredentials: If the current password does not match.
            MTAuthSamePassword: If the new password repeats the current one.

        Notes:
            - The current password is verified even though the caller is already
              authenticated. A token left behind on a shared machine is exactly
              the situation where somebody else would change the password, and
              knowing the old one is what distinguishes the holder from whoever
              found the session.
            - Refusing an unchanged password matters most on this path: the
              temporary one is a credential a second person has seen, and
              "changing" it to itself would clear the flag while leaving that
              credential live.
        """
        self.logger.info("Changing the password for account %s.", user.id)
        if not user.hashed_password or not self.verify(
            current_password, user.hashed_password
        ):
            self.logger.warning(
                "Refused a password change for %s: the current password is wrong.",
                user.id,
            )
            raise MTAuthInvalidCredentials("The current password is incorrect.")
        if self.verify(new_password, user.hashed_password):
            self.logger.warning(
                "Refused a password change for %s: the new password repeats "
                "the old one.",
                user.id,
            )
            raise MTAuthSamePassword(
                "The new password must differ from the current one."
            )

        updated = await self.users.update(
            user.model_copy(
                update={
                    "hashed_password": self.hash(new_password),
                    "must_change_password": False,
                    "password_changed_at": datetime.now(UTC),
                }
            )
        )
        if updated is None:
            self.logger.error(
                "Account %s vanished between the check and the password write.",
                user.id,
            )
            raise MTAuthInvalidCredentials("The account no longer exists.")
        self.logger.info(
            "Account %s changed its password; it is now fully usable.",
            updated.id,
        )
        return updated

    async def update_account(
        self, user: User, full_name: str, email: str, language: Language
    ) -> User:
        """Change the display name, sign-in address and language of an account.

        Args:
            user (User): The account being changed, taken from the credential.
            full_name (str): The display name to store.
            email (str): The address to sign in with from now on.
            language (Language): The language to read the application, and
                receive its documents, in.

        Returns:
            User: The updated account.

        Raises:
            MTAuthEmailAlreadyRegistered: If another account already signs in
                with that address.
            MTAuthUnknownAccount: If the account disappeared mid-write.

        Notes:
            - **The account being changed comes from the credential, never from a
              parameter.** There is no ``user_id`` to pass, so the only account a
              caller can reach through this method is their own — the same shape
              the self-service quote and profile routes use.
            - The address is checked for a clash before the write rather than
              after. The column is unique, so a duplicate would otherwise surface
              as a database integrity error and be answered as a 500: a spelling
              mistake reported as a server fault, with nothing telling the holder
              what to correct.
            - An address that resolves to the *same* account is not a clash. The
              screen sends both fields on every save, so somebody changing only
              their display name sends their own address back unchanged, and
              refusing that would make the name uneditable.
            - **The language is stored, not merely displayed.** It decides what
              language the quotes emailed to customers come out in, and those
              are built by a background webhook with no browser attached to
              read a header from. A preference kept only in the browser could
              not reach it.
        """
        self.logger.info("Updating the account details of %s.", user.id)
        self.logger.debug(
            "Requested display name %r and address %r for account %s.",
            full_name,
            email,
            user.id,
        )
        existing = await self.users.get_by_email(email)
        if existing is not None and existing.id != user.id:
            self.logger.warning(
                "Refused to move account %s to %s: it is already registered.",
                user.id,
                email,
            )
            raise MTAuthEmailAlreadyRegistered(
                "That address is already used by another account."
            )

        updated = await self.users.update(
            user.model_copy(
                update=dict(
                    zip(("first_name", "last_name"), User.name_parts(full_name))  # noqa: E501
                )
                | {"email": email, "language": language}
            )
        )
        if updated is None:
            self.logger.error(
                "Account %s vanished between the check and the account write.",
                user.id,
            )
            raise MTAuthUnknownAccount("The account no longer exists.")
        self.logger.info(
            "Account %s updated its own details; documents in %s.",
            updated.id,
            updated.language.value,
        )
        return updated

    def require_password_change_done(self, user: User) -> None:
        """Refuse an account that has not yet changed its temporary password.

        Args:
            user (User): The account making a request.

        Raises:
            MTAuthPasswordChangeRequired: If the account must still change its
                password.

        Notes:
            **This is what makes the change mandatory rather than suggested.**
            An account issued a temporary password can sign in — it has to, in
            order to change it — and without this it could then do everything
            else with a credential somebody else typed. The middleware calls
            this for every request except the change itself.
        """
        if user.must_change_password:
            self.logger.warning(
                "Account %s attempted to act before changing its temporary password.",  # noqa: E501
                user.id,
            )
            raise MTAuthPasswordChangeRequired(
                "You must change your temporary password before using the application."  # noqa: E501
            )

    async def authenticate(self, email: str, password: str) -> User:
        """Verify a sign-in and return the account.

        Args:
            email (str): The sign-in address.
            password (str): The plaintext password.

        Returns:
            User: The authenticated account.

        Raises:
            MTAuthInvalidCredentials: If no account matches, or the password is
                wrong.
            MTAuthUserInactive: If the account is deactivated.

        Notes:
            The password is verified even when no account was found, against a
            hash that cannot match. Skipping the comparison would make the
            unknown-address path measurably faster and leak which addresses are
            registered through timing alone.
        """
        self.logger.debug("Authenticating %s.", email)
        user = await self.users.get_by_email(email)
        if user is None:
            self.verify(password, self.DUMMY_HASH)
            self.logger.warning("Sign-in failed for %s: no such account.", email)  # noqa: E501
            raise MTAuthInvalidCredentials("Incorrect email address or password.")  # noqa: E501
        if not self.verify(password, user.hashed_password):
            self.logger.warning("Sign-in failed for %s: wrong password.", email)  # noqa: E501
            raise MTAuthInvalidCredentials("Incorrect email address or password.")  # noqa: E501
        if not user.is_active:
            self.logger.warning("Sign-in refused for %s: account inactive.", email)  # noqa: E501
            raise MTAuthUserInactive(
                "This account is deactivated. Contact an administrator."
            )
        self.logger.info("Authenticated %s as %s.", email, user.role.value)
        return user

    async def issue_token(self, user: User) -> AccessToken:
        """Mint an access token for an authenticated account.

        Args:
            user (User): The account to issue for.

        Returns:
            AccessToken: The signed token and its lifetime.

        Raises:
            MTAuthMissingSecret: If the signing secret is not configured.
        """
        self.logger.debug("Issuing a token for %s.", user.email)
        return self.issue(str(user.email))

    async def resolve_token(self, token: str) -> User:
        """Return the account a bearer token identifies.

        Args:
            token (str): The bearer token.

        Returns:
            User: The account, freshly read from the store.

        Raises:
            MTAuthInvalidToken: If the token is invalid or names an account
                that no longer exists.
            MTAuthUserInactive: If the account has since been deactivated.

        Notes:
            The account is re-read on every request rather than trusted from
            the token's claims. A deletion, a demotion or a deactivation
            therefore takes effect at once, instead of when the token expires.
        """
        subject = self.read_subject(token)
        user = await self.users.get_by_email(subject)
        if user is None:
            self.logger.warning(
                "Token names %s, which no longer has an account.", subject
            )
            raise MTAuthInvalidToken("The account no longer exists.")
        if not user.is_active:
            self.logger.warning("Token names the deactivated account %s.", subject)  # noqa: E501
            raise MTAuthUserInactive("This account is deactivated.")
        self.logger.debug("Resolved token to %s (%s).", subject, user.role.value)  # noqa: E501
        return user

    async def delete_account(self, user_id: str, requested_by: User) -> None:
        """Remove an account outright.

        Args:
            user_id (str): The account to remove.
            requested_by (User): The administrator asking.

        Raises:
            MTAuthLastAdmin: If this is the last administrator, or the caller's
                own account.

        Notes:
            - **Deactivating is the ordinary way to stop somebody signing in**;
              this is for accounts that should never have existed — one raised
              in error, and the fixtures a test campaign is obliged to remove
              after itself. Removing a person who worked here erases who
              validated what.
            - Refuses the caller's own account and refuses the last
              administrator, for the same reason
              :meth:`promote` and :meth:`set_active` do: an agency with no
              administrator cannot appoint one, and the mistake is unrecoverable
              through the product.
        """
        if user_id == requested_by.id:
            self.logger.warning(
                "Account %s attempted to delete itself.", requested_by.email
            )
            raise MTAuthLastAdmin("An administrator may not delete their own account.")
        existing = await self.users.get(user_id)
        if existing is None:
            self.logger.warning("Account %s does not exist; nothing deleted.", user_id)  # noqa: E501
            raise MTAuthUnknownAccount(f"No account {user_id!r} exists.")
        if existing.role is UserRole.ADMIN and await self.users.count_admins() <= 1:  # noqa: E501
            self.logger.warning(
                "Refused to delete %s: it is the last administrator.",
                existing.email,
            )
            raise MTAuthLastAdmin(
                "The last administrator cannot be deleted; there would be "
                "nobody able to appoint another."
            )
        await self.users.delete(user_id)
        self.logger.info("Deleted account %s.", user_id)

    async def promote(self, user_id: str, role: UserRole) -> Optional[User]:
        """Change an account's role.

        Args:
            user_id (str): The account to change.
            role (UserRole): The role to grant.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.

        Raises:
            MTAuthLastAdmin: If the change would remove the last administrator.

        Notes:
            Refusing to demote the last administrator is what stops an
            installation locking itself out of running plannings and promoting
            managers — a state no remaining account could repair.
        """
        current = await self.users.get(user_id)
        if current is None:
            self.logger.warning("Promotion requested for absent account %s.", user_id)  # noqa: E501
            return None
        demoting_an_admin = (
            current.role is UserRole.ADMIN and role is not UserRole.ADMIN
        )
        if demoting_an_admin and await self.users.count_admins() <= 1:
            self.logger.error(
                "Refused to demote %s: it is the last administrator.", user_id
            )
            raise MTAuthLastAdmin(
                "This is the last administrator account. Promote another account first."
            )
        self.logger.info("Changing account %s role to %s.", user_id, role.value)  # noqa: E501
        return await self.users.set_role(user_id, role)

    async def set_active(self, user_id: str, is_active: bool) -> Optional[User]:  # noqa: E501
        """Enable or disable sign-in for an account.

        Args:
            user_id (str): The account to change.
            is_active (bool): Whether sign-in is permitted.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.

        Raises:
            MTAuthLastAdmin: If deactivating would remove the last usable
                administrator.
        """
        current = await self.users.get(user_id)
        if current is None:
            self.logger.warning(
                "Activation change requested for absent account %s.", user_id
            )
            return None
        deactivating_an_admin = current.role is UserRole.ADMIN and not is_active  # noqa: E501
        if deactivating_an_admin and await self.users.count_admins() <= 1:
            self.logger.error(
                "Refused to deactivate %s: it is the last administrator.",
                user_id,
            )
            raise MTAuthLastAdmin(
                "This is the last administrator account. It cannot be deactivated."
            )
        self.logger.info("Setting account %s active to %s.", user_id, is_active)  # noqa: E501
        return await self.users.set_active(user_id, is_active)

    def hash(self, password: str) -> str:
        """Return the bcrypt hash of a password.

        Args:
            password (str): The plaintext password.

        Returns:
            str: The hash, including its salt and cost parameters.
        """
        self.logger.debug("Hashing a password.")
        truncated = password.encode("utf-8")[: self.MAX_PASSWORD_BYTES]
        return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")

    def verify(self, password: str, hashed_password: Optional[str]) -> bool:
        """Return whether a password matches a stored hash.

        Args:
            password (str): The plaintext password to check.
            hashed_password (Optional[str]): The stored hash, or ``None`` when
                the account has no password set.

        Returns:
            bool: ``True`` when the password matches.

        Notes:
            - An account with no hash returns ``False`` rather than raising, so
              the sign-in path reports the same failure whether the account has
              no password or the wrong one. Distinguishing the two would tell an
              attacker which addresses are registered.
            - A malformed stored hash is treated the same way. bcrypt raises on
              one, and letting that propagate would turn a corrupt row into a
              500 that reveals the account exists.
        """
        if not hashed_password:
            self.logger.warning("Verification attempted against an unset password.")
            return False
        try:
            return bcrypt.checkpw(
                password.encode("utf-8")[: self.MAX_PASSWORD_BYTES],
                hashed_password.encode("utf-8"),
            )
        except ValueError as exc:
            self.logger.error("Stored password hash is malformed: %s.", exc)
            return False

    def issue(self, subject: str) -> AccessToken:
        """Mint an access token for an account.

        Args:
            subject (str): The account's sign-in address.

        Returns:
            AccessToken: The signed token and its lifetime.

        Raises:
            MTAuthMissingSecret: If the signing secret is not configured.
        """
        expires_in = self.config.access_token_expire_minutes * 60
        issued_at = datetime.now(UTC)
        claims: Dict[str, Union[str, int]] = {
            self.SUBJECT_CLAIM: subject,
            self.ISSUED_AT_CLAIM: int(issued_at.timestamp()),
            self.EXPIRY_CLAIM: int(
                (issued_at + timedelta(seconds=expires_in)).timestamp()
            ),
        }
        try:
            token = jwt.encode(
                claims,
                self.config.get_jwt_secret(),
                algorithm=self.config.jwt_algorithm,
            )
        except MTAuthConfigMissingSecret as exc:
            self.logger.error("Cannot issue a token: %s.", exc)
            raise MTAuthMissingSecret(str(exc)) from exc
        self.logger.info(
            "Issued an access token for %s, valid for %d second(s).",
            subject,
            expires_in,
        )
        return AccessToken(access_token=token, expires_in=expires_in)

    def read_subject(self, token: str) -> str:
        """Return the account address a token was issued for.

        Args:
            token (str): The bearer token.

        Returns:
            str: The subject claim.

        Raises:
            MTAuthMissingSecret: If the signing secret is not configured.
            MTAuthInvalidToken: If the token is malformed, expired, signed with
                the wrong key, carries no subject, or is a stream token.

        Notes:
            - Only the configured algorithm is accepted. Passing the whole
              supported set would let a token nominate its own algorithm, which
              is the ``alg`` confusion attack.
            - A **stream token is refused here**. It is a weaker credential —
              it travels in a query string, so it reaches referrer headers,
              proxy logs and browser history — and accepting it as a bearer
              token would make every one of those places a full session.
        """
        claims = self._decode(token)
        if claims.get(self.SCOPE_CLAIM) == self.STREAM_SCOPE:
            self.logger.warning("Rejected a stream token used as a bearer credential.")  # noqa: E501
            raise MTAuthInvalidToken("This token cannot be used for the API.")
        subject = claims.get(self.SUBJECT_CLAIM)
        if not isinstance(subject, str) or not subject:
            self.logger.error("Accepted token carries no usable subject claim.")  # noqa: E501
            raise MTAuthInvalidToken("The access token carries no subject.")
        self.logger.debug("Read token subject %s.", subject)
        return subject

    def issue_stream_token(self, user: User) -> AccessToken:
        """Mint a short-lived credential for an event stream.

        Args:
            user (User): The account opening the stream.

        Returns:
            AccessToken: The signed stream token and its lifetime.

        Raises:
            MTAuthMissingSecret: If the signing secret is not configured.

        Notes:
            ``EventSource`` cannot set an ``Authorization`` header, so the only
            way a browser can authenticate a stream is to put something in the
            URL. Putting the *session* token there would leak a twelve-hour
            credential into referrer headers, proxy logs and browser history.
            This one lives for a minute, is scoped so
            :meth:`read_subject` refuses it everywhere else, and is fetched
            fresh each time the stream reconnects.
        """
        expires_in = self.STREAM_TOKEN_TTL_SECONDS
        issued_at = datetime.now(UTC)
        claims: Dict[str, Union[str, int]] = {
            self.SUBJECT_CLAIM: str(user.email),
            self.SCOPE_CLAIM: self.STREAM_SCOPE,
            self.ISSUED_AT_CLAIM: int(issued_at.timestamp()),
            self.EXPIRY_CLAIM: int(
                (issued_at + timedelta(seconds=expires_in)).timestamp()
            ),
        }
        try:
            token = jwt.encode(
                claims,
                self.config.get_jwt_secret(),
                algorithm=self.config.jwt_algorithm,
            )
        except MTAuthConfigMissingSecret as exc:
            self.logger.error("Cannot issue a stream token: %s.", exc)
            raise MTAuthMissingSecret(str(exc)) from exc
        self.logger.info(
            "Issued a stream token for %s, valid for %d second(s).",
            user.email,
            expires_in,
        )
        return AccessToken(access_token=token, expires_in=expires_in)

    async def resolve_stream_token(self, token: str) -> User:
        """Return the account a stream token identifies.

        Args:
            token (str): The stream token from the query string.

        Returns:
            User: The account, freshly read from the store.

        Raises:
            MTAuthInvalidToken: If the token is invalid, is not scoped for a
                stream, or names an account that no longer exists.
            MTAuthUserInactive: If the account has since been deactivated.

        Notes:
            The scope is checked in both directions: a session token is refused
            here just as a stream token is refused by :meth:`read_subject`. A
            credential that works in two places is two places it can leak from.
        """
        claims = self._decode(token)
        if claims.get(self.SCOPE_CLAIM) != self.STREAM_SCOPE:
            self.logger.warning("Rejected a non-stream token on the event stream.")
            raise MTAuthInvalidToken("This token cannot open an event stream.")
        subject = claims.get(self.SUBJECT_CLAIM)
        if not isinstance(subject, str) or not subject:
            raise MTAuthInvalidToken("The stream token carries no subject.")
        user = await self.users.get_by_email(subject)
        if user is None:
            raise MTAuthInvalidToken("The account no longer exists.")
        if not user.is_active:
            raise MTAuthUserInactive("This account is deactivated.")
        return user

    def generate_temporary_password(self) -> str:
        """Return a fresh temporary password.

        Returns:
            str: A password of :attr:`LENGTH` characters drawn from
            :attr:`ALPHABET`.

        Notes:
            The value is returned and never retained. It is shown to the
            administrator once, at the moment the account is created, and the
            only stored form is its hash — so a password lost between the
            screen and the new employee has to be regenerated rather than
            looked up, which is the correct trade.
        """
        password = "".join(
            secrets.choice(self.TEMPORARY_PASSWORD_ALPHABET)
            for _ in range(self.TEMPORARY_PASSWORD_LENGTH)
        )
        self.logger.info(
            "Generated a %d-character temporary password.",
            self.TEMPORARY_PASSWORD_LENGTH,
        )
        return password
