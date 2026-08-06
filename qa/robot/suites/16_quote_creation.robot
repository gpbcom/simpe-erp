*** Settings ***
Documentation    Writing a quote from the manager's screen, and issuing it.
...
...              Suite 05 covers the *journey* across two roles and the broker.
...              This one covers the screen a manager actually writes a quote on,
...              and the one thing that used to fail on every seeded quote:
...              validation refusing a quote whose lines were never priced.
...
...              **Idempotent by construction.** Every quote it writes carries a
...              unique reference, and the teardown deletes exactly those. It
...              never validates a *seeded* quote: validation is one-way, so
...              doing that would consume a fixture the second run needs.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Quote Screen As A Manager
Suite Teardown   Finish The Quote Suite
Test Teardown    Take A Screenshot On Failure


*** Variables ***
@{WRITTEN_QUOTE_IDS}


*** Test Cases ***
A Manager Can Write A Quote From The Quotes Screen
    [Documentation]    The screen exists, and it stores what it is given.
    ...
    ...    There was no way to create a quote from this screen at all: the grid
    ...    showed what already existed and offered no way to add to it.
    [Tags]    smoke    quotes
    ${suffix}=    Unique Suffix
    Write A Quote    QA-NEW-${suffix}

    ${stored}=    Quote With Reference    QA-NEW-${suffix}
    Should Not Be Equal    ${stored}    ${None}    msg=The quote was not stored.
    Append To List    ${WRITTEN_QUOTE_IDS}    ${stored}[id]
    Should Be Equal    ${stored}[status]    draft

The Server Prices What The Screen Sends
    [Documentation]    The dialog carries no amounts, and the stored quote has them.
    ...
    ...    **The bug this suite was written for, one level up.** A quote whose
    ...    lines are unpriced cannot be validated, and the seeder used to write
    ...    exactly that — so the whole seeded validation queue failed with "has
    ...    no priced lines". Pricing belongs to the server, and this asserts it
    ...    happens without the browser sending a single figure.
    [Tags]    smoke    quotes    pricing
    ${suffix}=    Unique Suffix
    Write A Quote    QA-PRICE-${suffix}

    ${stored}=    Quote With Reference    QA-PRICE-${suffix}
    Append To List    ${WRITTEN_QUOTE_IDS}    ${stored}[id]
    Should Not Be Empty    ${stored}[lines]
    FOR    ${line}    IN    @{stored}[lines]
        Should Not Be Equal    ${line}[total_ttc]    ${None}
        ...    msg=Line ${line}[name] came back without an amount.
    END

The Tax Is Computed From The Category The Screen Chose
    [Documentation]    **What the VAT on every quote now depends on.**
    ...
    ...    The dialog sets the line to comfort care, and the server must tax it
    ...    at 20% rather than at whatever the catalogue entry happens to say.
    ...    Asserted as a ratio of the stored amounts rather than against a
    ...    fixed figure: the agency's hourly rate is configuration, so a
    ...    hard-coded total would go stale the first time it changed, and the
    ...    test would then fail for a reason that has nothing to do with tax.
    [Tags]    smoke    quotes    pricing    vat
    ${suffix}=    Unique Suffix
    Write A Quote    QA-VAT-${suffix}

    ${stored}=    Quote With Reference    QA-VAT-${suffix}
    Append To List    ${WRITTEN_QUOTE_IDS}    ${stored}[id]
    ${line}=    Set Variable    ${stored}[lines][0]
    Should Be Equal    ${line}[service_category]    comfort
    ...    msg=The category the dialog chose was not stored on the line.

    ${ratio}=    Evaluate
    ...    round(float($line["vat_amount"]) / float($line["total_ht"]), 3)
    Should Be Equal As Numbers    ${ratio}    0.2
    ...    msg=Comfort care was taxed at ${ratio} rather than at 20%.

Validating A Quote Changes Its Status And Issues It
    [Documentation]    The status moves, and the offer gets its dates.
    ...
    ...    Validating **is** issuing here — there is no second button — so a
    ...    quote that reached ``sent`` with no issue date and no expiry was an
    ...    offer whose copy carried neither. Asserted on the stored record
    ...    rather than on the screen: what the grid shows is a rendering of
    ...    this, and only this is the fact.
    [Tags]    smoke    quotes
    ${suffix}=    Unique Suffix
    Write A Quote    QA-VALID-${suffix}
    ${stored}=    Quote With Reference    QA-VALID-${suffix}
    Append To List    ${WRITTEN_QUOTE_IDS}    ${stored}[id]

    # Submitted as the **manager**, because the manager wrote it: only a
    # quote's author may submit it, and this one came from the manager's own
    # screen. Submitting as the assistant is a 403 — correctly, since it is not
    # their quote.
    Submit Quote Through The API    ${MANAGER_EMAIL}    ${stored}[id]
    Quote Status Should Become    ${stored}[id]    pending-validation

    Navigate To    /quotes
    # Reloaded because the submission happened over the API, behind the screen's
    # back. The quote list is cached for thirty seconds, so a tab click alone
    # renders the list as it was before the quote joined the queue.
    Reload
    Click    [data-testid="quote-tab-pending"]
    Wait For Elements State    [data-testid="validate-QA-VALID-${suffix}"]    visible
    Click    [data-testid="validate-QA-VALID-${suffix}"]

    Quote Status Should Become    ${stored}[id]    sent
    ${issued}=    Quote With Reference    QA-VALID-${suffix}
    Should Not Be Equal    ${issued}[issued_on]     ${None}
    ...    msg=A sent quote carries no issue date.
    Should Not Be Equal    ${issued}[valid_until]   ${None}
    ...    msg=A sent quote carries no expiry.

The Validated Quote Leaves The Pending Tab
    [Documentation]    The status change, as the manager sees it.
    ...
    ...    The queue is the pending tab, so a quote that has been ruled on
    ...    leaving it *is* the status change made visible. A grid that kept
    ...    showing it would have a manager validating the same quote twice.
    [Tags]    quotes
    Navigate To    /quotes
    Reload
    Click    [data-testid="quote-tab-pending"]
    Wait For Elements State    [data-testid="quotes-grid"]    visible
    ${references}=    Get Text    [data-testid="quotes-grid"]
    Should Not Contain    ${references}    QA-VALID-


*** Keywords ***
Open The Quote Screen As A Manager
    [Documentation]    Sign in and land on the quotes screen.
    Open The Application Without Coverage
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tabs"]    visible

Write A Quote
    [Documentation]    Fill the new-quote dialog and store it.
    ...
    ...    The customer and the service are chosen by index rather than by name:
    ...    which customers and which catalogue entries exist follows from the
    ...    seeded spread, and a name written here goes stale the first time that
    ...    changes.
    [Arguments]    ${reference}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="new-quote"]    visible
    Click                      [data-testid="new-quote"]
    Wait For Elements State    [data-testid="new-quote-dialog"]    visible
    Fill Text            [data-testid="new-quote-reference"]    ${reference}
    Select Options By    [data-testid="new-quote-customer"]     index    1
    Select Options By    [data-testid="new-quote-type-0"]       index    1
    # The VAT category is part of writing a quote now, not a property of the
    # service. Set explicitly so the assertion below knows what to expect.
    Select Options By    [data-testid="new-quote-category-0"]   value    comfort
    Wait For Elements State    [data-testid="new-quote-submit"]    enabled
    Click                      [data-testid="new-quote-submit"]
    Wait For Elements State    [data-testid="new-quote-dialog"]    detached

Quote With Reference
    [Documentation]    Return the stored quote with a reference, or ``None``.
    [Arguments]    ${reference}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [q for q in $response.json() if q["reference"]=="""${reference}"""]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Finish The Quote Suite
    [Documentation]    Remove every quote this run wrote, then close the browser.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Remove The Quotes Created By This Run    @{WRITTEN_QUOTE_IDS}
    Close The Application Without Coverage
    IF    '${status}' != 'PASS'
        Fail    Quotes this run wrote were left behind: ${error}
    END

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
