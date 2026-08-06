*** Settings ***
Documentation    Changing an account's own password, and the gate a new one meets.
...
...              **Run entirely against an account this suite creates.** A
...              password is the one thing the campaign could change that would
...              stop it from ever running again: a seeded credential altered by
...              a test that then failed before restoring it locks every later
...              run out of the application, and no teardown can recover what it
...              no longer knows. So nothing here touches a seeded account. An
...              assistant record and an account are created in the setup and
...              deleted in the teardown, and the passwords are this run's own.
...
...              That also buys the forced-change journey, which nothing else
...              covered: a freshly created account cannot reach any screen
...              until it replaces the password somebody else chose for it, and
...              only a brand-new account can demonstrate that.
...
...              **The tests are ordered.** Each leaves the account holding a
...              different password, and the next signs in with it.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Create A Throwaway Assistant And Account
Suite Teardown   Remove The Throwaway Account And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${THROWAWAY_HCA_ID}      ${EMPTY}
${THROWAWAY_USER_ID}     ${EMPTY}
${THROWAWAY_EMAIL}       ${EMPTY}
${TEMPORARY_PASSWORD}    ${EMPTY}
# Both comfortably over the minimum length the policy enforces, and different
# from each other: the service refuses a "change" that repeats the current
# password, which is exactly what a temporary one being reused would be.
${FIRST_PASSWORD}        QaChosenPassphrase-1!
${SECOND_PASSWORD}       QaChosenPassphrase-2!


*** Test Cases ***
A New Account Cannot Reach The Application At All
    [Documentation]    **The gate, from the only side that can demonstrate it.**
    ...
    ...    An account created by a manager holds a password a *second person*
    ...    has seen. Until it is replaced the middleware refuses every request
    ...    the account makes except the change itself, so the application is not
    ...    merely hidden — it is unreachable. Asserted on a brand-new account,
    ...    because an account that has already changed its password can never
    ...    show this again.
    [Tags]    smoke    account    access
    Sign In Expecting The Forced Change
    Wait For Elements State    [data-testid="password-submit"]    visible
    ${shell}=    Get Element Count    [data-testid="nav--my-account"]
    Should Be Equal As Integers    ${shell}    0
    ...    msg=A new account reached the application before changing its password.

Changing The Temporary Password Admits The Account
    [Documentation]    The other half: the gate opens, rather than merely closing.
    [Tags]    smoke    account
    Fill Text    [data-testid="current-password"]    ${TEMPORARY_PASSWORD}
    Fill Text    [data-testid="new-password"]        ${FIRST_PASSWORD}
    Click    [data-testid="password-submit"]
    Wait For Elements State    [data-testid="nav--my-account"]    visible

The Account Page Renders For A Brand-New Assistant
    [Documentation]    Nothing on it depends on there being history to show.
    ...
    ...    A seeded assistant has quotes, absences and a photograph. This one
    ...    has none of them, which is the state every real assistant is in on
    ...    their first morning — and a page that only renders once something has
    ...    happened is a page nobody sees working.
    [Tags]    smoke    account
    Navigate To    /me
    Wait For Elements State    [data-testid="account-section"]     visible
    Wait For Elements State    [data-testid="password-section"]    visible
    Get Property    [data-testid="account-email"]    value    ==    ${THROWAWAY_EMAIL}

The Confirmation Must Match Before Anything Can Be Sent
    [Documentation]    A typo would become a credential nobody knows.
    ...
    ...    The confirmation field is the browser's own — the server has no way
    ...    to tell a mistyped new password from an intended one, so this is the
    ...    only place the mistake can be caught.
    [Tags]    smoke    account
    Fill Text    [data-testid="account-current-password"]    ${FIRST_PASSWORD}
    Fill Text    [data-testid="account-new-password"]        ${SECOND_PASSWORD}
    Fill Text    [data-testid="account-confirm-password"]    ${SECOND_PASSWORD}x
    Get Element States    [data-testid="save-password"]    contains    disabled
    [Teardown]    Clear The Password Fields

The Three Fields Are Required
    [Documentation]    A blank current password would be a change with no proof.
    [Tags]    account
    Fill Text    [data-testid="account-new-password"]        ${SECOND_PASSWORD}
    Fill Text    [data-testid="account-confirm-password"]    ${SECOND_PASSWORD}
    Get Element States    [data-testid="save-password"]    contains    disabled
    [Teardown]    Clear The Password Fields

The Current Password Is Required To Change It
    [Documentation]    **Being signed in is not enough.**
    ...
    ...    A session left open on a shared machine is exactly the case where
    ...    somebody else would change the password, and knowing the old one is
    ...    what tells the holder apart from whoever found the browser. Asserted
    ...    with a wrong one, which changes nothing and so can be run every time.
    [Tags]    smoke    account    access
    Fill Text    [data-testid="account-current-password"]    NotThePassword-9!
    Fill Text    [data-testid="account-new-password"]        ${SECOND_PASSWORD}
    Fill Text    [data-testid="account-confirm-password"]    ${SECOND_PASSWORD}
    Click    [data-testid="save-password"]
    Wait For Elements State    [data-testid="password-section-error"]    visible

    # And the old password still works, which is the part that matters: an
    # error message shown while the password had in fact changed would be worse
    # than no message at all.
    Sign In Through The API    ${THROWAWAY_EMAIL}    ${FIRST_PASSWORD}
    [Teardown]    Clear The Password Fields

A Correct Change Is Confirmed And Takes Effect
    [Documentation]    The whole point, asserted on the server rather than on screen.
    [Tags]    smoke    account
    Fill Text    [data-testid="account-current-password"]    ${FIRST_PASSWORD}
    Fill Text    [data-testid="account-new-password"]        ${SECOND_PASSWORD}
    Fill Text    [data-testid="account-confirm-password"]    ${SECOND_PASSWORD}
    Wait For Elements State    [data-testid="save-password"]    enabled
    Click    [data-testid="save-password"]
    Wait For Elements State    [data-testid="password-section-saved"]    visible

    # The confirmation on screen is what the browser was told. This is what the
    # server actually holds.
    Sign In Through The API    ${THROWAWAY_EMAIL}    ${SECOND_PASSWORD}

The Replaced Password No Longer Signs In
    [Documentation]    A change that left the old one working would change nothing.
    [Tags]    smoke    account    access
    ${body}=    Create Dictionary
    ...    email=${THROWAWAY_EMAIL}    password=${FIRST_PASSWORD}
    POST
    ...    ${API_URL}/api/v1/auth/login
    ...    json=${body}    expected_status=401

A Changed Password Does Not Re-Impose The Forced Change
    [Documentation]    The flag is cleared once, not set again by every change.
    ...
    ...    Worth its own test: the temporary-password flag and an ordinary
    ...    change go through the same service method, and a flag set rather
    ...    than cleared there would trap the holder on the change screen for
    ...    ever, each change demanding another.
    [Tags]    smoke    account
    Sign Out
    Sign In As    ${THROWAWAY_EMAIL}    ${SECOND_PASSWORD}
    Wait For Elements State    [data-testid="nav--my-account"]    visible
    ${forced}=    Get Element Count    [data-testid="password-submit"]
    Should Be Equal As Integers    ${forced}    0
    [Teardown]    Sign Out


*** Keywords ***
Sign In Expecting The Forced Change
    [Documentation]    Sign in without waiting for a shell that will not render.
    ...
    ...    ``Sign In As`` waits for the top bar, and a brand-new account never
    ...    gets one: it is routed straight to the change-password screen, and
    ...    the shared keyword would wait out its timeout and fail before this
    ...    suite could assert the very thing it exists to assert.
    Fill Text    [data-testid="login-email"]       ${THROWAWAY_EMAIL}
    Fill Text    [data-testid="login-password"]    ${TEMPORARY_PASSWORD}
    Click    [data-testid="login-submit"]

Create A Throwaway Assistant And Account
    [Documentation]    Build an assistant and an account nobody else uses.
    ...
    ...    Two records, because an account must name an assistant record to
    ...    belong to. Both are deleted in the teardown, by identifier.
    ${suffix}=    Unique Suffix
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}

    # The coordinate is supplied rather than left to be resolved. Constructing
    # an address geocodes it through Nominatim when it carries none, and the
    # public instance is rate-limited to one request a second and will block an
    # address that arrives on every run of the campaign.
    ${address}=    Create Dictionary
    ...    street=12 rue de Rivoli
    ...    postal_code=75004
    ...    city=Paris
    ...    country=France
    ...    latitude=${48.8566}
    ...    longitude=${2.3522}
    # The agency is read from the caller's own account rather than named. Every
    # person in this system belongs to one, and the record is refused without
    # it — a fixture that carried a literal identifier would be a fixture that
    # creates staff in whichever agency that string happens to be.
    ${me}=    GET
    ...    ${API_URL}/api/v1/me/account    headers=${headers}    expected_status=200
    ${hca}=    Create Dictionary
    ...    first_name=QA
    ...    last_name=Credentials-${suffix}
    ...    phone_number=+33612345678
    ...    email=qa.hca.${suffix}@simple-erp.fr
    ...    address=${address}
    ...    contract_type=cdi
    ...    company_id=${me.json()}[company_id]
    ${created}=    POST
    ...    ${API_URL}/api/v1/hcas
    ...    json=${hca}    headers=${headers}    expected_status=201
    Set Suite Variable    ${THROWAWAY_HCA_ID}    ${created.json()}[id]

    ${account}=    Create Dictionary
    ...    hca_id=${created.json()}[id]
    ...    email=qa.account.${suffix}@simple-erp.fr
    ...    full_name=QA Credentials ${suffix}
    ${issued}=    POST
    ...    ${API_URL}/api/v1/auth/accounts
    ...    json=${account}    headers=${headers}    expected_status=201
    Set Suite Variable    ${THROWAWAY_EMAIL}    qa.account.${suffix}@simple-erp.fr
    Set Suite Variable    ${THROWAWAY_USER_ID}    ${issued.json()}[user_id]
    Set Suite Variable    ${TEMPORARY_PASSWORD}    ${issued.json()}[temporary_password]

    Open The Application

Remove The Throwaway Account And Close
    [Documentation]    Delete both records, and say so if either survives.
    ...
    ...    The account first: it holds a foreign key to the assistant record,
    ...    and deleting the record out from under it would either fail or leave
    ...    an account bound to nothing. Both are attempted even if the first
    ...    fails, so one stuck record does not strand the other as well.
    ${account}=    Run Keyword And Ignore Error    Delete The Throwaway Account
    ${assistant}=    Run Keyword And Ignore Error    Delete The Throwaway Assistant
    Close The Application
    Should Be Equal    ${account}[0]    PASS
    ...    msg=The throwaway account survived: ${account}[1]
    Should Be Equal    ${assistant}[0]    PASS
    ...    msg=The throwaway assistant record survived: ${assistant}[1]

Delete The Throwaway Account
    [Documentation]    Remove the account this run created.
    Run Keyword And Return If    '${THROWAWAY_USER_ID}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/users/${THROWAWAY_USER_ID}
    ...    headers=${headers}    expected_status=any
    Should Contain    ${{ [204, 404] }}    ${response.status_code}

Delete The Throwaway Assistant
    [Documentation]    Remove the assistant record this run created.
    Run Keyword And Return If    '${THROWAWAY_HCA_ID}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/hcas/${THROWAWAY_HCA_ID}
    ...    headers=${headers}    expected_status=any
    Should Contain    ${{ [204, 404] }}    ${response.status_code}

Clear The Password Fields
    [Documentation]    Leave the form empty for the next test.
    ...
    ...    Three separate fills rather than a reload: a reload would discard the
    ...    error alert one of these tests has just asserted, and the next test
    ...    would be starting from a page it never saw rendered.
    FOR    ${field}    IN
    ...    account-current-password    account-new-password    account-confirm-password
        Run Keyword And Ignore Error    Fill Text    [data-testid="${field}"]    ${EMPTY}
    END

Take A Screenshot On Failure
    [Documentation]    Keep the picture of whatever went wrong.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
