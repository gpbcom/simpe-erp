*** Settings ***
Documentation    The assistant's customer cards, and the manager's directory.
...
...              The two screens answer the same question for different people,
...              and the difference between them is the scoping rule: an
...              assistant sees the customers they serve, a manager sees the
...              agency's book. Both are covered, and so is the difference.

Library          Browser
Library          Collections
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Portfolio
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Portfolio Renders As Cards
    [Documentation]    Cards, not a table: this screen is opened on a phone.
    [Tags]    smoke    customers
    Wait For Elements State    [data-testid="customer-cards"]    visible
    ${cards}=    Get Element Count    [data-testid="customer-cards"] .MuiCard-root
    Should Be True    ${cards} > 0

Each Card Carries A Name, An Address And A Status
    [Documentation]    What an assistant needs between two visits.
    [Tags]    customers
    ${text}=    Get Text    [data-testid="customer-cards"] .MuiCard-root >> nth=0
    # A five-digit postcode: the address is really on the card, not just a name.
    Should Match Regexp    ${text}    \\d{5}
    Should Match Regexp    ${text}    (Actif|Arrêté)

The Search Narrows The Cards
    [Documentation]    Typing a name reduces what is shown.
    [Tags]    smoke    customers    filtering
    ${all}=    Get Element Count    [data-testid="customer-cards"] .MuiCard-root
    ${name}=    First Customer Surname
    Fill Text    [data-testid="customer-search"]    ${name}
    Sleep    2s
    ${filtered}=    Get Element Count    [data-testid="customer-cards"] .MuiCard-root
    Should Be True    ${filtered} > 0
    Should Be True    ${filtered} <= ${all}
    [Teardown]    Clear The Customer Search

A Search Matching Nobody Shows The Empty State
    [Documentation]    A sentence rather than a blank grid.
    [Tags]    customers    filtering    empty-state
    Fill Text    [data-testid="customer-search"]    ZZZZ-personne-de-ce-nom
    Sleep    2s
    Wait For Elements State    [data-testid="customers-empty"]    visible
    [Teardown]    Clear The Customer Search

Opening A Card Shows The Contact Details
    [Documentation]    The drawer carrying the telephone number and the address.
    [Tags]    smoke    customers
    Click    [data-testid="customer-cards"] .MuiCard-root >> nth=0
    Wait For Elements State    [data-testid="customer-detail"]    visible
    ${detail}=    Get Text    [data-testid="customer-detail"]
    Should Match Regexp    ${detail}    \\+33
    Should Match Regexp    ${detail}    \\d{5}
    Should Contain        ${detail}    @
    [Teardown]    Close The Drawer

The Drawer Closes Again
    [Documentation]    An assistant can get back to the list.
    [Tags]    customers
    Click    [data-testid="customer-cards"] .MuiCard-root >> nth=0
    Wait For Elements State    [data-testid="customer-detail"]    visible
    Click    .MuiBackdrop-root
    Wait For Elements State    [data-testid="customer-detail"]    detached

An Assistant Sees Fewer Customers Than The Agency Has
    [Documentation]    The scoping rule, asserted as a number.
    ...
    ...    **The test the whole portfolio rests on.** A home-care record carries
    ...    an address, a telephone number and a care schedule; there is no
    ...    reason for every assistant to hold every one of them. If these two
    ...    counts are equal, the scoping is not being applied and the screen is
    ...    the agency's directory wearing a different heading.
    [Tags]    smoke    customers    access
    ${mine}=    Count Of My Customers
    ${agency}=    Count Of Agency Customers
    Should Be True    ${mine} > 0
    Should Be True    ${mine} < ${agency}


*** Keywords ***
Open The Portfolio
    Open The Application
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/customers
    Wait For Elements State    [data-testid="customer-cards"]    visible

Clear The Customer Search
    Fill Text    [data-testid="customer-search"]    ${EMPTY}
    Sleep    2s

Close The Drawer
    Run Keyword And Ignore Error    Click    .MuiBackdrop-root
    Run Keyword And Ignore Error
    ...    Wait For Elements State    [data-testid="customer-detail"]    detached

First Customer Surname
    [Documentation]    Return a surname that is certainly in the portfolio.
    ...
    ...    Read from the API rather than hard-coded, so the suite does not break
    ...    the day the seeded portfolio changes.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/customers    headers=${headers}    expected_status=200
    ${customers}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${customers}
    RETURN    ${customers}[0][last_name]

Count Of My Customers
    [Documentation]    How many the assistant is entitled to see.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/customers?size=200
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${{ len($response.json()) }}

Count Of Agency Customers
    [Documentation]    How many the agency has altogether.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers?size=200
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${{ len($response.json()) }}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
