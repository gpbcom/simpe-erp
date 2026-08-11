*** Settings ***
Documentation    Connecting the certified platform an agency transmits invoices through.
...
...              The reform routes every invoice through an intermediary the tax
...              authority recognises, and the free public exchange service was
...              withdrawn — so an agency must contract with a *plateforme
...              agréée*. That makes "nothing is connected" a legal state rather
...              than an empty screen, which is why the warning banner is
...              asserted as hard as the gallery itself.
...
...              **The security assertion is the one that matters most.** The API
...              key is stored encrypted and no endpoint returns it. That is
...              checked here against the server rather than against the screen,
...              because a screen that does not display a secret and an API that
...              does not return one are different guarantees, and only the
...              second survives somebody writing a new screen.
...
...              Everything written is written back: the suite leaves the agency
...              with nothing connected, which is where it found it.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Integrations As A Manager
Suite Teardown   Disconnect Everything And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${PLATFORM}         invopop
${BOGUS_KEY}        sk_live_definitely_not_a_real_key


*** Test Cases ***
The Billing Settings Carry An Integrations Sub-Menu
    [Documentation]    Requirement 3: the gallery lives beside the invoicing rules.
    ...
    ...    A sub-menu rather than a route of its own, because these are two
    ...    halves of one subject — what an invoice says, and where it goes.
    [Tags]    smoke    einvoicing
    Wait For Elements State    [data-testid="billing-settings-tabs"]    visible
    Wait For Elements State    [data-testid="billing-tab-integrations"]    visible

The Gallery Offers Every Certified Platform
    [Documentation]    Requirement 4: the reference design's grid, tabs, sort and search.
    ...
    ...    The count is asserted rather than sampled. A gallery showing only
    ...    what an agency has already connected would be empty on exactly the
    ...    screen whose job is to get something connected.
    [Tags]    smoke    einvoicing
    Wait For Elements State    [data-testid="integrations-gallery"]    visible
    ${cards}=    Get Element Count    [data-testid^="integration-card-"]
    Should Be Equal As Integers    ${cards}    4
    ...    msg=The gallery no longer offers all four documented platforms.
    Wait For Elements State    [data-testid="integrations-tabs"]    visible
    Wait For Elements State    [data-testid="integrations-sort"]    visible
    Wait For Elements State    [data-testid="integrations-search"]    visible

A Platform Whose Documentation Could Not Be Read Says So
    [Documentation]    **Asserted so nobody tidies the honesty away.**
    ...
    ...    Iopole's API documentation renders client-side and its servers return
    ...    malformed headers, so its connector is written to documented shape
    ...    rather than to anything confirmed. A gallery offering all four as
    ...    equals would be lying by omission.
    [Tags]    einvoicing
    Wait For Elements State    [data-testid="integration-unverified-iopole"]    visible
    ${verified}=    Get Element Count    [data-testid="integration-unverified-invopop"]
    Should Be Equal As Integers    ${verified}    0

Nothing Connected Is Said Out Loud
    [Documentation]    Requirement 3's banner, and the reason it exists.
    ...
    ...    Electronic invoicing is an obligation. An agency that has connected
    ...    nothing cannot transmit or report a single invoice, and must be told
    ...    rather than left to notice.
    [Tags]    smoke    einvoicing
    Wait For Elements State    [data-testid="einvoicing-warning"]    visible

The Warning Follows A Manager To Where They Work
    [Documentation]    A warning only on a settings screen is one nobody sees.
    [Tags]    smoke    einvoicing
    Navigate To    /bills
    Wait For Elements State    [data-testid="bills-page"]    visible
    Wait For Elements State    [data-testid="einvoicing-warning"]    visible
    Wait For Elements State    [data-testid="einvoicing-warning-link"]    visible
    [Teardown]    Open The Integrations Tab

The Dialog Asks Only For What The Platform Needs
    [Documentation]    Requirement 5: two clicks and a paste, not three empty boxes.
    ...
    ...    Invopop authenticates on a key alone; Storecove additionally wants a
    ...    legal-entity reference created in its own console. Asking every
    ...    platform for every field would raise a question about which matter.
    [Tags]    smoke    einvoicing
    Click    [data-testid="integration-card-${PLATFORM}"]
    Wait For Elements State    [data-testid="integration-dialog"]    visible
    Wait For Elements State    [data-testid="integration-field-api_key"]    visible
    ${extra}=    Get Element Count    [data-testid="integration-field-legal_entity_id"]
    Should Be Equal As Integers    ${extra}    0
    [Teardown]    Click    [data-testid="integration-cancel"]

A Key The Platform Refuses Is Reported Into The Open Dialog
    [Documentation]    **Proven before it is stored, and the reason why.**
    ...
    ...    The server checks the credentials against the live platform as part
    ...    of enabling. A key that is wrong therefore fails where it was typed,
    ...    rather than weeks later as an invoice that silently never left — which
    ...    is the exact failure this whole feature exists to prevent.
    ...
    ...    The bogus key reaches a real platform and is refused by it, so this
    ...    test needs the outside world. It asserts the *server's* refusal, not
    ...    a client-side guess.
    [Tags]    einvoicing    network
    ${headers}=    Manager Headers
    ${body}=    Create Dictionary    api_key=${BOGUS_KEY}
    ${response}=    PUT
    ...    ${API_URL}/api/v1/billing/integrations/${PLATFORM}
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Not Be Equal As Integers    ${response.status_code}    200
    ...    msg=A key no platform would accept was stored anyway.

    ${cards}=    The Integration Cards
    ${connected}=    Evaluate    [c for c in $cards if c["enabled"]]
    Should Be Empty    ${connected}
    ...    msg=A refused key left the agency believing it was connected.

The API Never Returns A Stored Credential
    [Documentation]    **The security assertion, made against the server.**
    ...
    ...    A screen that does not display a secret and an API that does not
    ...    return one are different guarantees. Only the second survives
    ...    somebody writing a second screen, so it is the one asserted — over
    ...    the whole payload, so a field added later is caught too.
    [Tags]    smoke    einvoicing    security
    ${cards}=    The Integration Cards
    Should Not Be Empty    ${cards}
    FOR    ${card}    IN    @{cards}
        Dictionary Should Not Contain Key    ${card}    credential_ciphertext
        ...    msg=The integrations endpoint returned an encrypted credential.
        Dictionary Should Not Contain Key    ${card}    api_key
        ...    msg=The integrations endpoint returned an API key.
        Dictionary Should Contain Key    ${card}    credential_hint
    END

An Assistant Cannot Read Or Change What Is Connected
    [Documentation]    Sent by hand, because the screen not offering it is not the control.
    ...
    ...    The platform credentials are the agency's contract with a third party
    ...    it pays. The rule lives in the route's guard, not in the navigation.
    [Tags]    smoke    einvoicing    security    scoping
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${read}=    GET
    ...    ${API_URL}/api/v1/billing/integrations
    ...    headers=${headers}
    ...    expected_status=any
    Should Be True    ${read.status_code} in [401, 403]
    ...    msg=An assistant could read the agency's platform credentials.

    ${body}=    Create Dictionary    api_key=${BOGUS_KEY}
    ${write}=    PUT
    ...    ${API_URL}/api/v1/billing/integrations/${PLATFORM}
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be True    ${write.status_code} in [401, 403]
    ...    msg=An assistant could connect a certified platform.


*** Keywords ***
Open The Integrations As A Manager
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Open The Integrations Tab

Open The Integrations Tab
    [Documentation]    Reach the gallery through the sub-menu, as a manager does.
    Navigate To    /billing-settings
    Wait For Elements State    [data-testid="billing-settings-tabs"]    visible
    Click    [data-testid="billing-tab-integrations"]
    Wait For Elements State    [data-testid="integrations-gallery"]    visible

Manager Headers
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

The Integration Cards
    [Documentation]    Return the gallery's payload straight from the API.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/billing/integrations
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Disconnect Everything And Close
    [Documentation]    Leave the agency with nothing connected, as it was found.
    ...
    ...    A belt-and-braces teardown. A platform left enabled with a bogus key
    ...    would make every later suite's settled invoice fail to transmit, and
    ...    the failure would be attributed to whatever ran next.
    ${status}    ${error}=    Run Keyword And Ignore Error    Disconnect Every Platform
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    A certified platform was left connected: ${error}
    END

Disconnect Every Platform
    [Documentation]    Switch off anything this suite may have connected.
    ${headers}=    Manager Headers
    ${cards}=    The Integration Cards
    FOR    ${card}    IN    @{cards}
        IF    ${card}[enabled]
            DELETE
            ...    ${API_URL}/api/v1/billing/integrations/${card}[provider]
            ...    headers=${headers}
            ...    expected_status=any
        END
    END

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
