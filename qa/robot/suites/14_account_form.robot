*** Settings ***
Documentation    The assistant's own form: every field, saving, and what is locked.
...
...              Suite 02 covers the *rule* — certifications and contract type
...              are read-only. This one covers the form as a form: each of the
...              seven editable fields, the save round trip, the confirmation,
...              and the address change that re-geocodes. Everything it writes
...              it writes back, so it runs twice with the same result.

Library          Browser
Library          Collections
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Account Form
Suite Teardown   Restore The Assistant And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
&{ORIGINAL}


*** Test Cases ***
The Portrait Renders With A Fallback
    [Documentation]    A photograph, or the initials that stand in for one.
    [Tags]    smoke    account
    Wait For Elements State    [data-testid="profile-avatar"]    visible
    ${content}=    Get Text    [data-testid="profile-avatar"]
    ${images}=     Get Element Count    [data-testid="profile-avatar"] img
    Should Be True    ${images} > 0 or len("""${content}""".strip()) > 0

Every Editable Field Is Populated
    [Documentation]    The form opens on the stored record, not on blanks.
    ...
    ...    A form that renders empty and then fills in is a form an operator
    ...    starts typing into before it loads, and overwrites their own work.
    [Tags]    smoke    account
    FOR    ${field}    IN
    ...    profile-first-name    profile-last-name      profile-phone-number
    ...    profile-email         profile-street         profile-postal-code
    ...    profile-city          profile-country
        ${value}=    Get Attribute    [data-testid="${field}"]    value
        Should Not Be Empty    ${value}    msg=${field} rendered empty.
    END

The Whole Record Is On The Screen
    [Documentation]    Every field the system holds, not a chosen subset.
    ...
    ...    **The requirement this page exists to satisfy.** An account page that
    ...    shows part of the record leaves its holder unable to answer "what
    ...    does this system say about me?" — which is the question they opened
    ...    it to settle, and one they have a right to an answer to.
    [Tags]    smoke    account
    FOR    ${surface}    IN
    ...    profile-avatar          profile-first-name      profile-last-name
    ...    profile-phone-number           profile-email           profile-street
    ...    profile-postal-code     profile-city            profile-country
    ...    profile-licence-categories                      profile-licence-number
    ...    profile-licence-obtained-on                     profile-licence-expires-on
    ...    employment-section      certifications          absences-section
    ...    account-section         account-full-name       account-email
    ...    account-role            account-active          account-hca-id
    ...    account-company         password-section        record-section
    ...    record-created          record-updated
        Wait For Elements State    [data-testid="${surface}"]    attached
        ...    message=${surface} is missing from the account page.
    END

The Driving Licence Is Editable And Stored
    [Documentation]    The assistant's own document, and the planner reads it.
    ...
    ...    It decides which travel speed the planning computation routes them
    ...    at, so an assistant who passes their test wants it recorded the same
    ...    day rather than after somebody else gets round to it.
    [Tags]    account
    Fill Text    [data-testid="profile-licence-categories"]    B, BE
    Fill Text    [data-testid="profile-licence-number"]        QA-987654321
    Click    [data-testid="profile-save"]
    Wait For Elements State    [data-testid="profile-saved"]    visible

    ${stored}=    Stored Profile
    Should Be Equal    ${stored}[driving_license][number]    QA-987654321
    Should Contain     ${stored}[driving_license][categories]    B

The Photograph Can Be Changed By Its Owner
    [Documentation]    An assistant's portrait is their pin on the manager's map.
    ...
    ...    Being unable to set it was a gap rather than a restriction: it left
    ...    the one piece of personal data with real operational weight in
    ...    somebody else's hands. Only the control is asserted here — uploading
    ...    a real image is covered by the backend's own tests, and a fixture
    ...    photograph left on a seeded assistant would break the second run.
    [Tags]    account
    Wait For Elements State    [data-testid="upload-photo"]    visible
    Wait For Elements State    [data-testid="photo-input"]     attached

Saving A Changed Field Stores It And Confirms
    [Documentation]    The round trip, and the snackbar that reports it.
    [Tags]    smoke    account
    # Typed and confirmed as one retried step. The form is re-initialised from
    # the profile every time a query lands, so a refetch in flight from the
    # previous test can put the stored number back between the typing and the
    # click — the save then writes what was already there and reports success,
    # and the round trip this test is about never happened.
    Wait Until Keyword Succeeds    5s    500ms
    ...    Type And Confirm    profile-phone-number    +33600000188
    Click    [data-testid="profile-save"]
    Wait For Elements State    [data-testid="profile-saved"]    visible

    # Compared as digits, not as text. The server stores a telephone number in
    # its canonical form — `tel:+33-6-00-00-01-88` for what was typed as
    # `+33600000188` — so asserting the literal would be asserting the
    # formatting rather than that the edit was saved. The digits are the number;
    # the punctuation is a rendering decision the API is entitled to make.
    ${stored}=    Stored Profile
    ${digits}=    Digits Of    ${stored}[phone_number]
    Should Be Equal    ${digits}    33600000188

The Saved Value Survives A Reload
    [Documentation]    It was stored, not merely displayed.
    [Tags]    account
    Reload
    Wait For Elements State    [data-testid="profile-phone-number"]    visible
    ${value}=    Get Attribute    [data-testid="profile-phone-number"]    value
    ${digits}=    Digits Of    ${value}
    Should Be Equal    ${digits}    33600000188

Changing The Address Keeps It Geocoded
    [Documentation]    An assistant who moves must still be routable.
    ...
    ...    ``PostalAddress`` geocodes during validation, so a saved address
    ...    comes back with coordinates. Without them the assistant is dropped
    ...    from the next planning run — silently, because nothing else on this
    ...    screen would look different.
    [Tags]    account    geocoding
    Fill Text    [data-testid="profile-street"]         7 rue de Charonne
    Fill Text    [data-testid="profile-postal-code"]    75011
    Fill Text    [data-testid="profile-city"]           Paris
    Click    [data-testid="profile-save"]
    Wait For Elements State    [data-testid="profile-saved"]    visible

    ${stored}=    Stored Profile
    Should Be Equal    ${stored}[address][street]    7 rue de Charonne
    Should Not Be Equal    ${stored}[address][latitude]    ${None}

An Assistant Cannot Edit Their Qualifications Or Contract
    [Documentation]    The two fields an assistant does not own, seen locked.
    ...
    ...    Both are **visible** — hiding them would answer "what am I qualified
    ...    for?" with silence. What an assistant cannot do is change them: there
    ...    is no input and no save button in the section, only chips.
    [Tags]    smoke    account    access
    Wait For Elements State    [data-testid="employment-section"]    visible
    ${inputs}=    Get Element Count    [data-testid="employment-section"] input
    Should Be Equal As Integers    ${inputs}    0
    ${save}=    Get Element Count    [data-testid="save-employment"]
    Should Be Equal As Integers    ${save}    0
    Wait For Elements State    [data-testid="contract-type"]    visible

The Position Is Read-Only For Everybody
    [Documentation]    The role, shown and locked, with who sets it.
    ...
    ...    Locked for an administrator too, not only for an assistant. Promotion
    ...    happens on the workforce screen, and a page where somebody could
    ...    raise their own rank is a page with no rank at all.
    [Tags]    smoke    account    access
    Wait For Elements State    [data-testid="account-role"]    visible
    # A chip, not an input. Asserted by counting: the account section *does*
    # hold editable fields now — the display name and the sign-in address — so
    # "no inputs at all" would be the wrong assertion, and would have passed
    # for the wrong reason before either of those existed.
    ${role_inputs}=    Get Element Count    [data-testid="account-role"] input
    Should Be Equal As Integers    ${role_inputs}    0

The Account Fields An Assistant Owns Are Editable
    [Documentation]    A display name and a sign-in address, and only those.
    ...
    ...    Asserted rather than exercised: a changed sign-in address is what the
    ...    campaign signs in with, so a run that saved one and then failed
    ...    before restoring it would lock every later run out of the account.
    ...    Suite 19 does exercise the save, on a name it puts back.
    [Tags]    smoke    account
    Wait For Elements State    [data-testid="account-full-name"]    editable
    Wait For Elements State    [data-testid="account-email"]        editable
    Wait For Elements State    [data-testid="save-account"]         attached

Changing The Password Is Offered On The Account Page
    [Documentation]    Including the current one, which the server insists on.
    ...
    ...    The three fields are asserted, never filled. A changed password is
    ...    the one edit this campaign could make that would stop it from ever
    ...    running again.
    [Tags]    smoke    account
    Wait For Elements State    [data-testid="account-current-password"]    visible
    Wait For Elements State    [data-testid="account-new-password"]        visible
    Wait For Elements State    [data-testid="account-confirm-password"]    visible
    Wait For Elements State    [data-testid="save-password"]               attached

Absences Are The Assistant's Own To Declare
    [Documentation]    An absence removes somebody from the next planning run.
    ...
    ...    Leaving it read-only would mean telephoning somebody to say you were
    ...    on holiday. The controls are asserted rather than exercised: a
    ...    declared absence left behind would change what the planner does on
    ...    the next run of the campaign.
    [Tags]    account
    Wait For Elements State    [data-testid="absences-section"]    visible
    Wait For Elements State    [data-testid="absence-start"]       visible
    Wait For Elements State    [data-testid="add-absence"]         visible

Neither Locked Field Was Touched By Any Of That
    [Documentation]    Saving the form does not clear what it does not carry.
    ...
    ...    **This is the failure the endpoint was designed against.** The
    ...    request model has no ``certifications`` and no ``contract_type``, and
    ...    the service copies five fields onto the *stored* record rather than
    ...    rebuilding it — so a save cannot silently strip a qualification, a
    ...    licence, a photograph or a declared absence.
    [Tags]    smoke    account
    ${stored}=    Stored Profile
    Should Be Equal    ${stored}[contract_type]    ${ORIGINAL}[contract_type]
    Should Be Equal As Integers
    ...    ${{ len($stored["certifications"]) }}
    ...    ${ORIGINAL}[certification_count]

The Locked Fields Are Explained Rather Than Merely Disabled
    [Documentation]    A tooltip saying who owns them.
    ...
    ...    A disabled input says "you cannot type here". A locked chip with
    ...    "set by your manager" says who to ask, which is the difference
    ...    between a confused assistant and one who knows what to do next.
    [Tags]    account
    Hover    [data-testid="contract-type"]
    Wait For Elements State    .MuiTooltip-tooltip    visible
    Get Text    .MuiTooltip-tooltip    !=    ${EMPTY}


*** Keywords ***
Type And Confirm
    [Documentation]    Fill a field and assert it really holds what was typed.
    [Arguments]    ${testid}    ${value}
    Fill Text    [data-testid="${testid}"]    ${value}
    ${held}=    Get Attribute    [data-testid="${testid}"]    value
    Should Be Equal    ${held}    ${value}
    ...    msg=${testid} reverted to '${held}' after being typed into.

Digits Of
    [Documentation]    Return only the digits of a telephone number.
    ...
    ...    So a test can assert *which number* was stored without asserting how
    ...    the server chooses to punctuate it.
    [Arguments]    ${value}
    ${digits}=    Evaluate    "".join(c for c in $value if c.isdigit())
    RETURN    ${digits}

Open The Account Form
    [Documentation]    Sign in, open the form, and remember the starting state.
    Open The Application
    Sign In As    ${ASSISTANT_EMAIL}
    Remember The Original Profile
    Navigate To    /me
    Wait For Elements State    [data-testid="profile-first-name"]    visible

Remember The Original Profile
    [Documentation]    Snapshot what the suite must put back.
    ...
    ...    Taken before anything is typed, so the teardown restores the seeded
    ...    values rather than whatever a half-finished test left behind.
    ${profile}=    Stored Profile
    Set Suite Variable    &{ORIGINAL}
    ...    phone_number=${profile}[phone_number]
    ...    street=${profile}[address][street]
    ...    postal_code=${profile}[address][postal_code]
    ...    city=${profile}[address][city]
    ...    first_name=${profile}[first_name]
    ...    last_name=${profile}[last_name]
    ...    email=${profile}[email]
    ...    contract_type=${profile}[contract_type]
    ...    certification_count=${{ len($profile["certifications"]) }}

Stored Profile
    [Documentation]    Read the assistant's own record through the API.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/hca    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Restore The Assistant And Close
    [Documentation]    Put the seeded values back, then close the browser.
    ...
    ...    Through the API, so it runs even when the browser is sitting on a
    ...    failure. Without this the second run starts from the first run's
    ...    edits and the "every field is populated" test would still pass while
    ...    the seed had quietly drifted.
    ...
    ...    The restore is attempted first and reported last, with the browser
    ...    closed in between: a restore that fails must not leak a browser, and
    ...    must not pass quietly either. Ignoring it is what turns a fault in
    ...    this run into a mystery in the next one.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Restore The Original Profile
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    The seeded assistant was left modified. The next run starts dirty: ${error}
    END

Restore The Original Profile
    [Documentation]    Write the snapshot back.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    # Built with Create Dictionary rather than a multi-line Evaluate: Robot
    # splits a continued line on whitespace, so an inline dict literal arrives
    # as eight separate arguments.
    ${address}=    Create Dictionary
    ...    street=${ORIGINAL}[street]
    ...    postal_code=${ORIGINAL}[postal_code]
    ...    city=${ORIGINAL}[city]
    ...    country=France
    ${body}=    Create Dictionary
    ...    first_name=${ORIGINAL}[first_name]
    ...    last_name=${ORIGINAL}[last_name]
    ...    phone_number=${ORIGINAL}[phone_number]
    ...    email=${ORIGINAL}[email]
    ...    address=${address}
    PATCH    ${API_URL}/api/v1/me/hca    json=${body}    headers=${headers}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
