*** Settings ***
Documentation    Editing the services on a quote, from both sides of the rule.
...
...              A manager may edit any quote in the agency; an assistant may
...              edit only the ones they wrote. Both use the same dialog, and
...              the difference is which quotes they can open and which endpoint
...              saves them — so the two halves are tested against each other
...              here rather than in two places that could drift.
...
...              **Idempotent by construction.** Every quote it touches is one
...              it created, carrying a unique suffix, and the teardown removes
...              exactly those. The seeded book of quotes is never edited: a
...              line added to a seeded quote would still be there on the second
...              run, and the run after that would find a different fixture than
...              the one it was written against.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          DateTime
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Prepare The Editor Fixtures
Suite Teardown   Remove The Editor Fixtures And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
@{CREATED_QUOTE_IDS}
${OWN_QUOTE}        ${EMPTY}
${FOREIGN_QUOTE}    ${EMPTY}
${OWN_REFERENCE}    ${EMPTY}
${FOREIGN_REFERENCE}    ${EMPTY}


*** Test Cases ***
A Manager Can Open A Quote They Did Not Write
    [Documentation]    The whole point of the manager scope.
    ...
    ...    Opened on the assistant's quote specifically. A manager opening
    ...    their own would pass whether the scoping worked or not.
    [Tags]    smoke    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Get Text    [data-testid="quote-editor"]    contains    ${OWN_REFERENCE}
    [Teardown]    Cancel And Sign Out

The Editor Opens On What Is Stored
    [Documentation]    The quote's existing services, not a blank form.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Wait For Elements State    [data-testid="quote-line-0"]    visible
    ${duration}=    Get Property    [data-testid="line-duration-0"]    value
    Should Be Equal As Integers    ${duration}    60
    [Teardown]    Cancel And Sign Out

Saving Rewrites The Services And Reprices Them
    [Documentation]    **The test the dialog exists for.**
    ...
    ...    The duration is changed on screen and then read back from the API,
    ...    not from the grid the dialog just refreshed. And the total is
    ...    asserted to have *moved*, which is the only evidence that the server
    ...    repriced rather than storing what the browser sent: the dialog
    ...    deliberately computes no prices, so an unchanged total would mean
    ...    the new duration was never costed.
    [Tags]    smoke    quotes    editor
    ${before}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Fill Text    [data-testid="line-duration-0"]    120
    Wait For Elements State    [data-testid="save-quote-lines"]    enabled
    Click    [data-testid="save-quote-lines"]
    Wait For Elements State    [data-testid="quote-editor"]    detached

    ${after}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Should Be Equal As Integers    ${after}[lines][0][duration_minutes]    120
    Should Not Be Equal As Numbers
    ...    ${after}[lines][0][total_ttc]    ${before}[lines][0][total_ttc]
    ...    msg=The total did not move when the duration doubled, so nothing repriced.
    [Teardown]    Sign Out

A Line Can Be Added And The Quote Grows
    [Documentation]    Adding a service, filled in and saved.
    [Tags]    smoke    quotes    editor
    ${before}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    ${count}=    Get Length    ${before}[lines]
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}

    Click    [data-testid="add-line"]
    Wait For Elements State    [data-testid="quote-line-${count}"]    visible
    # Chosen by index rather than by name: which catalogue entries exist
    # follows from the seeded spread, and a name written here goes stale the
    # first time that changes. Index 1 skips the empty placeholder option.
    Select Options By    [data-testid="line-type-${count}"]    index    1
    ${service_date}=    Get Current Date    increment=21 days    result_format=%Y-%m-%d
    Fill Text    [data-testid="line-date-${count}"]    ${service_date}

    Wait For Elements State    [data-testid="save-quote-lines"]    enabled
    Click    [data-testid="save-quote-lines"]
    Wait For Elements State    [data-testid="quote-editor"]    detached

    ${after}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Length Should Be    ${after}[lines]    ${{ ${count} + 1 }}
    [Teardown]    Sign Out

Choosing A Service Names The Line After It
    [Documentation]    So an operator does not retype what they just picked.
    ...
    ...    The name stays editable — it is what the customer reads on the
    ...    printed quote — but it starts as the catalogue entry's own name.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    ${count}=    Get Element Count    css=[data-testid^="quote-line-"]
    Click    [data-testid="add-line"]
    ${name}=    Get Property    [data-testid="line-name-${count}"]    value
    Should Be Empty    ${name}
    Select Options By    [data-testid="line-type-${count}"]    index    1
    Get Property    [data-testid="line-name-${count}"]    value    !=    ${EMPTY}
    [Teardown]    Cancel And Sign Out

A Line Can Be Removed Again
    [Documentation]    The other half of the add control.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    ${before}=    Get Element Count    css=[data-testid^="quote-line-"]
    Click    [data-testid="add-line"]
    ${grown}=    Get Element Count    css=[data-testid^="quote-line-"]
    Should Be Equal As Integers    ${grown}    ${{ ${before} + 1 }}
    Click    [data-testid="remove-line-${before}"]
    ${shrunk}=    Get Element Count    css=[data-testid^="quote-line-"]
    Should Be Equal As Integers    ${shrunk}    ${before}
    [Teardown]    Cancel And Sign Out

Saving Is Refused While A Line Is Incomplete
    [Documentation]    A service with no date and no type would price as nothing.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Click    [data-testid="add-line"]
    Get Element States    [data-testid="save-quote-lines"]    contains    disabled
    [Teardown]    Cancel And Sign Out

Saving Is Refused Until Something Changes
    [Documentation]    An untouched quote has nothing to reprice.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Get Element States    [data-testid="save-quote-lines"]    contains    disabled
    [Teardown]    Cancel And Sign Out

Cancelling Leaves The Quote Exactly As It Was
    [Documentation]    A dialog that half-saves on dismissal is worse than none.
    [Tags]    smoke    quotes    editor
    ${before}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Fill Text    [data-testid="line-duration-0"]    240
    Click    [data-testid="cancel-quote-edit"]
    Wait For Elements State    [data-testid="quote-editor"]    detached
    ${after}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Should Be Equal As Integers
    ...    ${after}[lines][0][duration_minutes]    ${before}[lines][0][duration_minutes]
    [Teardown]    Sign Out

The Editor Says The Server Does The Pricing
    [Documentation]    So nobody reads the stored total as the new one.
    ...
    ...    The figure beside the buttons is what the server last priced, and it
    ...    goes stale the moment a line is touched. The hint is what says so.
    [Tags]    quotes    editor
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    Wait For Elements State    [data-testid="repricing-hint"]    visible
    Get Text    [data-testid="repricing-hint"]    !=    ${EMPTY}
    [Teardown]    Cancel And Sign Out

An Assistant Can Edit The Quote They Wrote
    [Documentation]    The self-service half, through the same dialog.
    [Tags]    smoke    quotes    editor
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    Click    [data-testid="edit-quote-${OWN_REFERENCE}"]
    Wait For Elements State    [data-testid="quote-editor"]    visible
    Fill Text    [data-testid="line-duration-0"]    90
    Wait For Elements State    [data-testid="save-quote-lines"]    enabled
    Click    [data-testid="save-quote-lines"]
    Wait For Elements State    [data-testid="quote-editor"]    detached
    ${after}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Should Be Equal As Integers    ${after}[lines][0][duration_minutes]    90
    [Teardown]    Sign Out

An Assistant Is Not Offered A Quote They Did Not Write
    [Documentation]    The manager's quote is not on the assistant's screen.
    [Tags]    quotes    editor    access
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    ${offered}=    Get Element Count    [data-testid="edit-quote-${FOREIGN_REFERENCE}"]
    Should Be Equal As Integers    ${offered}    0
    [Teardown]    Sign Out

The Server Refuses An Assistant Editing Somebody Else's Quote
    [Documentation]    **The check the scoping actually rests on.**
    ...
    ...    A missing button is a courtesy, not a control. The self-service route
    ...    takes no author from the payload — it compares the caller against the
    ...    quote's stored author — so a request naming a manager's quote is
    ...    refused however it is sent, including by hand as it is here.
    [Tags]    smoke    quotes    editor    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Editing Payload For    ${FOREIGN_QUOTE}
    PUT
    ...    ${API_URL}/api/v1/me/quotes/${FOREIGN_QUOTE}[id]/lines
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=403

A Manager Is Allowed The Very Same Edit
    [Documentation]    Which proves the refusal was about the author.
    ...
    ...    The same quote and the same payload, through the manager route. If
    ...    this failed too, the test above would prove only that the request was
    ...    malformed.
    [Tags]    smoke    quotes    editor    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Editing Payload For    ${FOREIGN_QUOTE}
    PUT
    ...    ${API_URL}/api/v1/quotes/${FOREIGN_QUOTE}[id]/lines
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=200

The VAT Category Is Chosen On The Line, Not Inherited
    [Documentation]    **The rule the tax on every quote now rests on.**
    ...
    ...    The same service is necessity care for one customer and comfort care
    ...    for another: help with washing under a care plan is billed at 5.5%,
    ...    and the same hour arranged privately at 20%. Which it is depends on
    ...    the customer, so it cannot be a property of the catalogue entry — it
    ...    is chosen when the quote is written, and stored on the line.
    ...
    ...    Asserted on the *stored* VAT, not on the dropdown: a control that
    ...    changes and a tax that does not is the failure worth catching.
    [Tags]    smoke    quotes    editor    vat
    ${before}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}

    Select Options By    [data-testid="line-category-0"]    value    comfort
    Wait For Elements State    [data-testid="save-quote-lines"]    enabled
    Click    [data-testid="save-quote-lines"]
    Wait For Elements State    [data-testid="quote-editor"]    detached

    ${after}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    Should Be Equal    ${after}[lines][0][service_category]    comfort
    # 20% against 5.5% on an unchanged total: the tax has to have moved, and
    # upwards. Asserting only that it changed would pass if it fell.
    Should Be True
    ...    ${after}[lines][0][vat_amount] > ${before}[lines][0][vat_amount]
    ...    msg=The category changed to comfort but the VAT did not rise.
    [Teardown]    Restore The Necessity Category

The Category Follows The Service Chosen, As A Suggestion
    [Documentation]    Offered from the catalogue, but still the operator's call.
    ...
    ...    Picking a service fills the category in with what that service
    ...    usually is, which saves a decision on the common case. It does not
    ...    lock it: the field stays editable, because only the person writing
    ...    the quote knows whether this customer's hours are under a care plan.
    [Tags]    quotes    editor    vat
    Sign In As    ${MANAGER_EMAIL}
    Open The Editor On    ${OWN_REFERENCE}
    ${count}=    Get Element Count    css=[data-testid^="quote-line-"]
    Click    [data-testid="add-line"]
    Select Options By    [data-testid="line-type-${count}"]    index    1
    ${suggested}=    Get Property    [data-testid="line-category-${count}"]    value
    Should Not Be Empty    ${suggested}

    Select Options By    [data-testid="line-category-${count}"]    value    comfort
    ${chosen}=    Get Property    [data-testid="line-category-${count}"]    value
    Should Be Equal    ${chosen}    comfort
    ...    msg=The category could not be overridden after choosing a service.
    [Teardown]    Cancel And Sign Out

A Quote Past Draft Offers No Edit Button
    [Documentation]    What the customer was sent stays what they were sent.
    ...
    ...    Run last, and on the fixture rather than on a seeded quote, because
    ...    it is the one test here that moves a quote out of ``draft`` — which
    ...    every test above needs it to be in.
    [Tags]    smoke    quotes    editor
    Submit Quote Through The API    ${ASSISTANT_EMAIL}    ${OWN_QUOTE}[id]
    Quote Status Should Become    ${OWN_QUOTE}[id]    pending-validation

    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    # Reloaded, not merely navigated to. The quote list is cached for thirty
    # seconds, and the submission above went through the API rather than the
    # screen, so nothing invalidated that cache. Without this the grid renders
    # the quote as it was before the submission and the test passes on a stale
    # draft — which is worse than failing, because it would keep passing.
    Reload
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    ${own}=    Get Element Count    [data-testid="edit-quote-${OWN_REFERENCE}"]
    Should Be Equal As Integers    ${own}    0
    Sign Out

    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Reload
    Click    [data-testid="quote-tab-pending"]
    Wait For Elements State    [data-testid="validate-${OWN_REFERENCE}"]    visible
    ${theirs}=    Get Element Count    [data-testid="edit-${OWN_REFERENCE}"]
    Should Be Equal As Integers    ${theirs}    0
    [Teardown]    Sign Out


*** Keywords ***
Prepare The Editor Fixtures
    [Documentation]    Create one quote per side of the rule, then open up.
    ...
    ...    Two quotes, not one: the assistant's proves a manager may edit what
    ...    they did not write, and the manager's proves an assistant may not.
    ${suffix}=    Unique Suffix
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type

    ${own}=    Create A Draft Quote As
    ...    ${ASSISTANT_EMAIL}    ${customer_id}    ${type_id}    ${suffix}-OWN
    Set Suite Variable    ${OWN_QUOTE}    ${own}
    Set Suite Variable    ${OWN_REFERENCE}    QA-${suffix}-OWN
    Append To List    ${CREATED_QUOTE_IDS}    ${own}[id]

    ${foreign}=    Create A Draft Quote As A Manager
    ...    ${customer_id}    ${type_id}    ${suffix}-MGR
    Set Suite Variable    ${FOREIGN_QUOTE}    ${foreign}
    Set Suite Variable    ${FOREIGN_REFERENCE}    QA-${suffix}-MGR
    Append To List    ${CREATED_QUOTE_IDS}    ${foreign}[id]

    Open The Application

Remove The Editor Fixtures And Close
    [Documentation]    Delete exactly this run's quotes, then close the browser.
    Remove The Quotes Created By This Run    @{CREATED_QUOTE_IDS}
    Close The Application

Open The Editor On
    [Documentation]    Open the manager's quote list and edit one by reference.
    ...
    ...    The draft tab lists every draft in the agency and the grid pages at
    ...    twenty-five, so a fixture buried on page three would not be
    ...    clickable. It never is: quotes come back ordered by reference
    ...    descending, and ``QA-`` sorts above the seeded ``DEV-`` references,
    ...    so this run's fixtures are the first rows. If the seeder ever adopts
    ...    a prefix later in the alphabet, this keyword is what breaks.
    [Arguments]    ${reference}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tab-draft"]    visible
    Click    [data-testid="quote-tab-draft"]
    Wait For Elements State    [data-testid="edit-${reference}"]    visible
    Click    [data-testid="edit-${reference}"]
    Wait For Elements State    [data-testid="quote-editor"]    visible

Restore The Necessity Category
    [Documentation]    Put the line back to necessity, then end the session.
    ...
    ...    Through the API rather than the screen: the test that changed it may
    ...    have failed with the dialog open, and clicking a control that might
    ...    not be there would fail the teardown for the same reason the test
    ...    did. The fixture is deleted at suite teardown anyway; this keeps the
    ...    tests after it starting from the state they were written against.
    ${quote}=    Quote Read By A Manager    ${OWN_QUOTE}[id]
    ${lines}=    Evaluate
    ...    [{**line, "service_category": "necessity"} for line in $quote["lines"]]
    ${payload}=    Create Dictionary
    ...    reference=${quote}[reference]
    ...    customer_id=${quote}[customer_id]
    ...    lines=${lines}
    ${body}=    Evaluate    json.dumps($payload)    modules=json
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    PUT
    ...    ${API_URL}/api/v1/quotes/${OWN_QUOTE}[id]/lines
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=200
    Sign Out

Cancel And Sign Out
    [Documentation]    Dismiss the dialog without saving, and end the session.
    ...
    ...    Both steps are attempted even when the first fails: a test that broke
    ...    with the dialog open would otherwise leave a session behind and fail
    ...    every test after it on a sign-out button it cannot see, hiding the
    ...    one real cause behind a run of false ones.
    Run Keyword And Ignore Error    Click    [data-testid="cancel-quote-edit"]
    Run Keyword And Ignore Error
    ...    Wait For Elements State    [data-testid="quote-editor"]    detached
    Sign Out

Editing Payload For
    [Documentation]    Return a quote's own lines as a line-replacement body.
    ...
    ...    Built from what the quote already holds, so the request differs from
    ...    a legitimate one only in who sends it. A payload with invented lines
    ...    could be refused as invalid rather than as forbidden, and the test
    ...    would pass for the wrong reason.
    [Arguments]    ${quote}
    ${payload}=    Create Dictionary
    ...    reference=${quote}[reference]
    ...    customer_id=${quote}[customer_id]
    ...    lines=${quote}[lines]
    ${body}=    Evaluate    json.dumps($payload)    modules=json
    RETURN    ${body}

Take A Screenshot On Failure
    [Documentation]    Keep the picture of whatever went wrong.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
