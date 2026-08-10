*** Settings ***
Documentation    The agency's own record, and what each service costs an hour.
...
...              Two screens that decide things the rest of the application only
...              reads: the agency's legal identity, and the hourly rate every
...              quote line is priced from. They are gated differently on
...              purpose — a manager sets prices because that is running the
...              week, and an administrator sets the agency's identity because
...              that is not — so both gates are walked from both sides.
...
...              **Idempotent by construction.** The catalogue entry it edits is
...              one it creates, retired and renamed by identifier in the
...              teardown. The agency is seeded and cannot be created, so its
...              details are snapshotted first and restored afterwards —
...              through the API, in a teardown that runs even when the test
...              that changed them failed.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Snapshot The Agency And Open
Suite Teardown   Restore The Agency And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${ORIGINAL_AGENCY}      ${EMPTY}
${QA_TYPE_CODE}         ${EMPTY}
${QA_TYPE_ID}           ${EMPTY}
# The French heading the removed column used to carry. Written out rather than
# read from the bundle: a test that asked i18n for the word would pass if the
# key were deleted along with the column, which is the case it must catch.
${CATEGORY_HEADING}     Catégorie


*** Test Cases ***
Mon Compte Is In The Navigation For Every Role
    [Documentation]    **The regression the screenshot showed.**
    ...
    ...    The account entry was marked assistant-only, so a manager and an
    ...    administrator saw a "Mon compte" heading with only "Mes devis" under
    ...    it — a section named after a screen it did not contain. The page
    ...    itself had already been fixed; the door to it had not, which made the
    ...    fix invisible to exactly the people it was for.
    [Tags]    smoke    navigation    account
    FOR    ${email}    IN    ${ASSISTANT_EMAIL}    ${MANAGER_EMAIL}    ${ADMIN_EMAIL}
        Sign In As    ${email}
        Wait For Elements State    [data-testid="nav--me"]    visible
        ...    message=${email} has no My account entry in the navigation.
        Click    [data-testid="nav--me"]
        Wait For Elements State    [data-testid="account-section"]    visible
        Sign Out
    END

The Navigation Offers No Entry That Goes Nowhere
    [Documentation]    Every entry shown reaches a screen.
    ...
    ...    A "Bénéficiaires" entry survived with no route behind it, so
    ...    clicking it silently redirected home — which reads as the click not
    ...    registering. Walked rather than reasoned about: this is the check
    ...    that fails when somebody adds a menu item before the screen.
    ...
    ...    The destination is read from each entry's own ``href`` rather than
    ...    derived from its test id. The id is built by replacing every slash
    ...    in the path with a dash, so ``/intervention-types`` becomes
    ...    ``nav--intervention-types`` — and reversing that is ambiguous, since
    ...    nothing says which dash used to be a slash. A test that guessed
    ...    would fail on the entries with hyphenated paths and look like a
    ...    routing bug.
    [Tags]    smoke    navigation
    Sign In As    ${ADMIN_EMAIL}
    ${entries}=    Get Elements    css=[data-testid^="nav--"]
    Should Not Be Empty    ${entries}
    FOR    ${entry}    IN    @{entries}
        ${testid}=    Get Attribute    ${entry}    data-testid
        ${href}=      Get Attribute    ${entry}    href
        Click    [data-testid="${testid}"]
        ${url}=    Get Url
        Should End With    ${url}    ${href}
        ...    msg=${testid} points at ${href} but landed on ${url}: a dead entry.
    END
    [Teardown]    Sign Out

The Administration Group Is Named For What It Holds
    [Documentation]    Not "Devis", which named one entry after another.
    [Tags]    navigation
    Sign In As    ${ADMIN_EMAIL}
    Wait For Elements State    [data-testid="nav--intervention-types"]    visible
    Wait For Elements State    [data-testid="nav--company"]                visible
    [Teardown]    Sign Out

A Manager Sees The Catalogue But Not The Agency
    [Documentation]    **The two gates, from the side that has one of them.**
    ...
    ...    A manager sets what the agency charges — that is running the week.
    ...    Its trading name and SIRET are not, and the one setting with an
    ...    outward effect decides whether strangers can apply for a job.
    [Tags]    smoke    navigation    access
    Sign In As    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="nav--intervention-types"]    visible
    ${agency}=    Get Element Count    [data-testid="nav--company"]
    Should Be Equal As Integers    ${agency}    0
    [Teardown]    Sign Out

A Manager Typing The Agency Address Is Turned Away
    [Documentation]    Hiding the entry is a courtesy; this is the control.
    ...
    ...    Asserted on where they *do* land rather than on a three-second wait
    ...    for the agency screen that is expected to time out. Waiting for an
    ...    absence proves nothing until the wait expires, costs the whole
    ...    timeout on every green run, and files a ``TimeoutError`` in the log
    ...    to say the test passed. The guard redirects, so there is a positive
    ...    outcome to wait for — and "sent back to the quotes" is the stronger
    ...    claim anyway.
    [Tags]    smoke    access
    Sign In As    ${MANAGER_EMAIL}
    # Typed, which is what the test is named for. ``Navigate To`` follows a
    # navigation entry, and the entry this one is about is precisely the one a
    # manager does not have — so it spent fifteen seconds waiting for a link
    # that is missing on purpose and failed on the wrong thing entirely.
    Go To    ${BASE_URL}/company
    Wait For Elements State    [data-testid="quote-tabs"]    visible
    ${forbidden}=    Get Element Count    [data-testid="company-section"]
    Should Be Equal As Integers    ${forbidden}    0
    ...    msg=A manager reached the agency screen by typing its address.
    [Teardown]    Sign Out

The Server Refuses A Manager Reading The Agency
    [Documentation]    Sent by hand, because the screen offers no way to.
    [Tags]    smoke    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    GET    ${API_URL}/api/v1/me/company    headers=${headers}    expected_status=403

An Administrator Sees Their Own Agency Without Naming It
    [Documentation]    The identifier comes from the credential.
    [Tags]    smoke    company
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-section"]    visible
    ${name}=    Get Property    [data-testid="company-name"]    value
    Should Not Be Empty    ${name}
    [Teardown]    Sign Out

The Agency's Details Can Be Changed And Are Stored
    [Documentation]    Saved for real, then put back by the teardown.
    [Tags]    smoke    company
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-name"]    visible
    ${suffix}=    Unique Suffix
    Fill Text    [data-testid="company-name"]    QA Agency ${suffix}
    Click    [data-testid="save-company"]
    Wait For Elements State    [data-testid="company-saved"]    visible

    ${stored}=    Agency As Stored
    Should Be Equal    ${stored}[name]    QA Agency ${suffix}
    [Teardown]    Restore The Agency And Sign Out

Saving The Agency With No Name Is Refused
    [Documentation]    The one field nothing else can work around.
    [Tags]    company
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-name"]    visible
    Fill Text    [data-testid="company-name"]    ${EMPTY}
    Get Element States    [data-testid="save-company"]    contains    disabled
    [Teardown]    Reload And Sign Out

The Applications Switch Explains What Closing Does
    [Documentation]    "Stop accepting" reads like it might discard the queue.
    ...
    ...    It does not: somebody who applied yesterday still deserves a
    ...    decision. The caption is the only thing that says so, so its absence
    ...    is a defect rather than a cosmetic loss.
    [Tags]    company
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-accepting"]    visible
    ${section}=    Get Text    [data-testid="company-section"]
    Should Not Be Empty    ${section}
    [Teardown]    Sign Out

A Privileged Field Cannot Be Smuggled Into The Agency Payload
    [Documentation]    **What keeps one agency out of another's record.**
    ...
    ...    The payload model carries no identifier, so a request naming another
    ...    agency is parsed without it and the caller's own is written instead.
    ...    Sent by hand: the screen has no such control, and testing the screen
    ...    would prove only that.
    [Tags]    smoke    company    access
    ${before}=    Agency As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${before}[name]
    ...    id=some-other-agency
    ...    is_accepting_applications=${before}[is_accepting_applications]
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=200

    ${after}=    Agency As Stored
    Should Be Equal    ${after}[id]    ${before}[id]

The Catalogue Shows What Every Service Costs An Hour
    [Documentation]    The screen a rate is actually set on.
    [Tags]    smoke    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="catalog-grid"]      visible
    Wait For Elements State    [data-testid="pricing-rules"]     visible
    Get Text    [data-testid="agency-rate"]    !=    ${EMPTY}
    [Teardown]    Sign Out

The Agency-Wide Rules Say They Are Not Editable Here
    [Documentation]    A read-only field that does not explain itself is a bug.
    ...
    ...    The default rate and the surcharges live in the deployment's
    ...    configuration. Showing them without saying so invites a manager to
    ...    look for the control that changes them.
    [Tags]    smoke    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="pricing-rules-readonly"]    visible
    Get Text    [data-testid="pricing-rules-readonly"]    !=    ${EMPTY}
    [Teardown]    Sign Out

The Catalogue Does Not Claim A VAT Category Per Service
    [Documentation]    **A column here would state something a quote can deny.**
    ...
    ...    The category used to be a column, and it read as a property of the
    ...    service. It is not: the same service is necessity care for one
    ...    customer and comfort care for another, so it is chosen on the quote
    ...    line. Showing it here would tell a manager a fact about the service
    ...    that the next quote written against it may contradict.
    ...
    ...    The entry still carries a *suggested* category, which fills the field
    ...    in when an operator picks the service — that lives in the dialog, and
    ...    the test below opens it.
    [Tags]    smoke    catalog    vat
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="catalog-grid"]    visible
    ${headers}=    Get Text    [data-testid="catalog-grid"] .MuiDataGrid-columnHeaders
    Should Not Contain    ${headers}    ${CATEGORY_HEADING}
    ...    msg=The catalogue still shows a VAT category column.
    ${cells}=    Get Element Count    css=[data-testid^="type-category-"]
    Should Be Equal As Integers    ${cells}    0
    [Teardown]    Sign Out

The Suggested Category Is Still Editable On The Entry
    [Documentation]    It is a default for new quote lines, not a rule.
    [Tags]    catalog    vat
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Click    [data-testid="edit-type-${QA_TYPE_CODE}"]
    Wait For Elements State    [data-testid="type-dialog"]      visible
    Wait For Elements State    [data-testid="type-category"]    editable
    [Teardown]    Close The Type Dialog And Sign Out

An Entry With No Rate Of Its Own Shows What It Inherits
    [Documentation]    **An empty cell would read as "free".**
    ...
    ...    A catalogue entry may name no rate, and then it bills at the agency
    ...    rate. The difference between "inherits 31,905 €" and "costs nothing"
    ...    is the difference between a correct quote and one that bills a
    ...    family nothing, so the grid prints the inherited figure.
    [Tags]    smoke    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="type-rate-${QA_TYPE_CODE}"]    visible
    ${shown}=    Get Text    [data-testid="type-rate-${QA_TYPE_CODE}"]
    Should Not Be Empty    ${shown}
    Should Match Regexp    ${shown}    [0-9]
    ...    msg=An entry inheriting the agency rate shows no figure at all.
    [Teardown]    Sign Out

Every Seeded Service Shows The Same Hourly Rate
    [Documentation]    One price across the catalogue, as the seed sets it.
    ...
    ...    The seeded catalogue bills every service at the agency rate, so a
    ...    demo total is checkable by hand — hours x the rate, times any
    ...    surcharge — and the only thing that varies between two lines is the
    ...    VAT their categories carry. A service that drifted to its own price
    ...    would make every worked example in the documentation wrong.
    ...
    ...    Compared on the money figure alone: an entry that names no rate of
    ...    its own renders the inherited one followed by "tarif de l'agence",
    ...    so the cells' full text differs even when the price does not.
    [Tags]    catalog    pricing
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="catalog-grid"]    visible

    @{cells}=    Create List
    ${rows}=    Get Elements    css=[data-testid^="type-rate-"]
    Should Not Be Empty    ${rows}
    FOR    ${cell}    IN    @{rows}
        ${text}=    Get Text    ${cell}
        Append To List    ${cells}    ${text}
    END

    # First money-looking token from each cell, deduplicated. One line, because
    # Robot splits a continued argument on whitespace and the tail would arrive
    # as `Evaluate`'s namespace.
    ${prices}=    Evaluate    sorted({__import__("re").search(r"[0-9][0-9 .,]*", c).group(0).strip() for c in $cells if __import__("re").search(r"[0-9]", c)})
    Length Should Be    ${prices}    1
    ...    msg=The catalogue shows more than one hourly rate: ${prices}
    [Teardown]    Sign Out

A Rate Can Be Set On One Service
    [Documentation]    The whole point of the screen, asserted on the server.
    [Tags]    smoke    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="edit-type-${QA_TYPE_CODE}"]    visible
    Click    [data-testid="edit-type-${QA_TYPE_CODE}"]
    Wait For Elements State    [data-testid="type-dialog"]    visible

    Fill Text    [data-testid="type-rate"]    42.50
    Wait For Elements State    [data-testid="save-type"]    enabled
    Click    [data-testid="save-type"]
    Wait For Elements State    [data-testid="type-dialog"]    detached

    ${stored}=    Catalogue Entry    ${QA_TYPE_ID}
    Should Be Equal As Numbers    ${stored}[base_hourly_rate_ht]    42.50
    [Teardown]    Sign Out

The Code Cannot Be Changed Once An Entry Exists
    [Documentation]    Every quote line already written refers to it.
    [Tags]    smoke    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Click    [data-testid="edit-type-${QA_TYPE_CODE}"]
    Wait For Elements State    [data-testid="type-dialog"]    visible
    Get Element States    [data-testid="type-code"]    contains    disabled
    [Teardown]    Close The Type Dialog And Sign Out

A Rate That Is Not A Positive Number Is Refused
    [Documentation]    Refused on the page, before it can be sent.
    [Tags]    catalog
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Click    [data-testid="edit-type-${QA_TYPE_CODE}"]
    Wait For Elements State    [data-testid="type-dialog"]    visible
    Fill Text    [data-testid="type-rate"]    -5
    Get Element States    [data-testid="save-type"]    contains    disabled
    [Teardown]    Close The Type Dialog And Sign Out

An Assistant Cannot Reach The Catalogue At All
    [Documentation]    They do not decide what the agency charges.
    [Tags]    smoke    catalog    access
    Sign In As    ${ASSISTANT_EMAIL}
    ${entry}=    Get Element Count    [data-testid="nav--intervention-types"]
    Should Be Equal As Integers    ${entry}    0
    Sign Out

    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    GET
    ...    ${API_URL}/api/v1/intervention-types/pricing-rules
    ...    headers=${headers}    expected_status=403


The Agency Can Declare Its Legal Identity
    [Documentation]    **What a quote must say about who is making the offer.**
    ...
    ...    A commercial offer has to identify the legal person behind it: the
    ...    form, the capital, the trade-register entry and the VAT number. None
    ...    of it was stored, so the emitted quote could name the agency and
    ...    nothing else — a document the recipient had no way to verify.
    ...
    ...    Asserted against the API rather than the form, because a screen that
    ...    keeps a typed value and never sends it looks identical to one that
    ...    works.
    [Tags]    smoke    company    legal-identity
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-legal-form"]    visible
    Fill Text    [data-testid="company-legal-form"]      SARL
    Fill Text    [data-testid="company-share-capital"]   10000
    Fill Text    [data-testid="company-rcs-number"]      RCS Paris B 123 456 789
    Fill Text    [data-testid="company-vat-number"]      FR12345678901
    Click    [data-testid="save-company"]
    Wait For Elements State    [data-testid="company-saved"]    visible

    ${stored}=    Agency As Stored
    Should Be Equal    ${stored}[legal_form]    SARL
    Should Be Equal    ${stored}[rcs_number]    RCS Paris B 123 456 789
    Should Be Equal    ${stored}[vat_number]    FR12345678901
    [Teardown]    Restore The Agency And Sign Out

A Malformed VAT Number Is Refused
    [Documentation]    It appears on every quote, so it is checked not stored.
    ...
    ...    A number with a digit missing is the kind of error nobody notices
    ...    until an accountant does. Sent by hand, because the form has no way
    ...    to report a 422 field by field.
    [Tags]    smoke    company    legal-identity
    ${agency}=    Agency As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${agency}[name]
    ...    vat_number=FR123
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=422

A Share Capital Of Zero Is Refused
    [Documentation]    A company with no capital declares nothing, not zero.
    ...
    ...    "Capital social 0,00 €" on a quote is a false declaration rather
    ...    than an empty field.
    [Tags]    company    legal-identity
    ${agency}=    Agency As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${agency}[name]
    ...    share_capital=${0}
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=422

A Manager Cannot Change The Agency's Legal Identity
    [Documentation]    Running the week is not declaring who the agency is.
    ...
    ...    The same administrator gate the rest of this screen has. Sent by
    ...    hand, because a manager has no navigation entry to it.
    [Tags]    smoke    company    legal-identity    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    name=Smuggled    legal_form=SAS
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=403

The Bank Details Are Recorded For SEPA Billing
    [Documentation]    A customer told what to pay has to be told where.
    ...
    ...    Asserted against the API rather than the form, as the legal-identity
    ...    case is: a screen that keeps a typed value and never sends it looks
    ...    identical to one that works.
    [Tags]    smoke    company    banking
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /company
    Wait For Elements State    [data-testid="company-iban"]    visible
    Fill Text    [data-testid="company-iban"]    FR76 3000 6000 0112 3456 7890 189
    Fill Text    [data-testid="company-bic"]     bnpafrpp
    Click    [data-testid="save-company"]
    Wait For Elements State    [data-testid="company-saved"]    visible

    ${stored}=    Agency As Stored
    Should Be Equal    ${stored}[iban]    FR7630006000011234567890189
    Should Be Equal    ${stored}[bic]     BNPAFRPP
    [Teardown]    Restore The Agency And Sign Out

An IBAN That Fails Its Checksum Is Refused
    [Documentation]    The two check digits exist to catch a transposition.
    ...
    ...    The digits below are transposed, not missing: every shape rule
    ...    passes and only the checksum fails, which is exactly the error
    ...    somebody makes copying twenty-seven characters by hand. Stored
    ...    unchecked, it surfaces weeks later as a payment that never arrived.
    [Tags]    smoke    company    banking
    ${agency}=    Agency As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${agency}[name]
    ...    iban=FR7630006000011234567809189
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=422

A Manager Reads The Agency's Account Masked
    [Documentation]    **The account number is the one field a leak can spend.**
    ...
    ...    A manager runs the agency's work and needs its address, telephone
    ...    number and registration; they have no reason to hold the account it
    ...    is paid into. The agency-wide routes hand back a masked projection,
    ...    and an administrator reads theirs whole at /me/company.
    [Tags]    smoke    company    banking    access
    ${agency}=    Agency As Stored
    ${admin}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${admin_headers}=    Authorisation Header    ${admin}
    ${body}=    Create Dictionary
    ...    name=${agency}[name]
    ...    iban=FR7630006000011234567890189
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${admin_headers}    expected_status=200

    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/companies/${agency}[id]
    ...    headers=${headers}    expected_status=200
    ${seen}=    Set Variable    ${response.json()}
    Should Be True    ${seen}[iban_is_masked]
    Should Not Be Equal    ${seen}[iban]    FR7630006000011234567890189
    Should Not Contain    ${seen}[iban]    300060000112345678
    [Teardown]    Restore The Agency And Sign Out

A Manager Cannot Change The Agency's Bank Details
    [Documentation]    The same administrator gate the rest of the screen has.
    [Tags]    smoke    company    banking    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=Smuggled
    ...    iban=FR7630006000011234567890189
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=403

A Logo Cannot Be Repointed Through The Profile Payload
    [Documentation]    **The logo is written only by the route that uploads it.**
    ...
    ...    Accepting one here would let a hand-crafted payload point the field
    ...    at an image this application does not own — and the delete path
    ...    would then be asked to remove somebody else's object. The payload
    ...    has no such field, so the value is ignored rather than refused.
    [Tags]    company    visual-identity    access
    ${agency}=    Agency As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${agency}[name]
    ...    logo_url=https://evil.example/tracker.png
    ${response}=    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=200
    Should Not Be Equal    ${response.json()}[logo_url]    https://evil.example/tracker.png
    [Teardown]    Restore The Agency And Sign Out

A Manager Cannot Change The Agency's Logo
    [Documentation]    A logo is how the agency identifies itself on a quote.
    [Tags]    smoke    company    visual-identity    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    DELETE
    ...    ${API_URL}/api/v1/me/company/logo
    ...    headers=${headers}    expected_status=403


*** Keywords ***
Snapshot The Agency And Open
    [Documentation]    Record the agency as found, then open the browser.
    ...
    ...    Recorded before anything runs. The agency is seeded and cannot be
    ...    created, so the only way this suite stays runnable twice is to put
    ...    back exactly what it found.
    ${agency}=    Agency As Stored
    Set Suite Variable    ${ORIGINAL_AGENCY}    ${agency}
    Create A Catalogue Entry With No Rate
    Open The Application

Restore The Agency And Close
    [Documentation]    Put the agency back, retire the fixture, close up.
    Run Keyword And Ignore Error    Restore The Agency
    Run Keyword And Ignore Error    Remove The Catalogue Fixture
    Close The Application

Restore The Agency And Sign Out
    [Documentation]    Undo a test that changed the agency, then end the session.
    Run Keyword And Ignore Error    Restore The Agency
    Sign Out

Reload And Sign Out
    [Documentation]    Discard an unsaved form, then end the session.
    Run Keyword And Ignore Error    Reload
    Sign Out

Close The Type Dialog And Sign Out
    [Documentation]    Dismiss without saving, then end the session.
    Run Keyword And Ignore Error    Click    [data-testid="cancel-type"]
    Sign Out

Agency As Stored
    [Documentation]    Read the agency as the server currently holds it.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/company    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Restore The Agency
    [Documentation]    Write back the agency exactly as the suite found it.
    Run Keyword And Return If    '${ORIGINAL_AGENCY}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${ORIGINAL_AGENCY}[name]
    ...    registration_number=${ORIGINAL_AGENCY}[registration_number]
    ...    contact_email=${ORIGINAL_AGENCY}[contact_email]
    ...    address=${ORIGINAL_AGENCY}[address]
    ...    is_accepting_applications=${ORIGINAL_AGENCY}[is_accepting_applications]
    ...    legal_form=${ORIGINAL_AGENCY}[legal_form]
    ...    share_capital=${ORIGINAL_AGENCY}[share_capital]
    ...    rcs_number=${ORIGINAL_AGENCY}[rcs_number]
    ...    vat_number=${ORIGINAL_AGENCY}[vat_number]
    ...    phone_number=${ORIGINAL_AGENCY}[phone_number]
    ...    iban=${ORIGINAL_AGENCY}[iban]
    ...    bic=${ORIGINAL_AGENCY}[bic]
    PUT
    ...    ${API_URL}/api/v1/me/company
    ...    json=${body}    headers=${headers}    expected_status=200

Create A Catalogue Entry With No Rate
    [Documentation]    Add a service that inherits the agency rate.
    ...
    ...    Created rather than borrowed from the seed: this suite changes the
    ...    entry's rate, and a seeded one left at 42,50 € would reprice every
    ...    quote a later run wrote against it.
    ${suffix}=    Generate Random String    6    [NUMBERS]
    Set Suite Variable    ${QA_TYPE_CODE}    QA${suffix}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=QA Service ${suffix}
    ...    code=QA${suffix}
    ...    service_category=necessity
    ...    is_active=${True}
    ${response}=    POST
    ...    ${API_URL}/api/v1/intervention-types
    ...    json=${body}    headers=${headers}    expected_status=201
    Set Suite Variable    ${QA_TYPE_ID}    ${response.json()}[id]
    RETURN    ${response.json()}

Catalogue Entry
    [Documentation]    Read one catalogue entry as the server holds it.
    [Arguments]    ${type_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/intervention-types/${type_id}
    ...    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Remove The Catalogue Fixture
    [Documentation]    Retire the entry this run created.
    ...
    ...    Retired rather than deleted outright, and then only if it exists:
    ...    the endpoint is a soft delete, because a quote written against a
    ...    service still has to print. A hard delete would orphan it.
    Run Keyword And Return If    '${QA_TYPE_ID}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    DELETE
    ...    ${API_URL}/api/v1/intervention-types/${QA_TYPE_ID}
    ...    headers=${headers}    expected_status=any

Take A Screenshot On Failure
    [Documentation]    Keep the picture of whatever went wrong.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
