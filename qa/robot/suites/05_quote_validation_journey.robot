*** Settings ***
Documentation    The journey the whole validation feature exists for.
...
...              An assistant writes a quote and submits it; the event crosses
...              RabbitMQ; the worker writes a notification; the API pushes it
...              over SSE; a manager sees the badge, validates the quote; and
...              the assistant is told. Every piece built in this change is on
...              that path, and this is the only test that exercises them
...              together.
...
...              **Idempotent by construction.** Every quote it creates carries
...              a unique suffix, and the teardown removes exactly the ones this
...              run made. The seeded data is never edited.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Prepare The Journey
Suite Teardown   Finish The Journey
Test Teardown    Take A Screenshot On Failure


*** Variables ***
@{CREATED_QUOTE_IDS}


*** Test Cases ***
An Assistant Submits A Quote And A Manager Is Notified
    [Documentation]    The full round trip, across two roles and the broker.
    [Tags]    smoke    journey

    # --- The assistant writes and submits -------------------------------
    ${suffix}=    Unique Suffix
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type
    ${quote}=    Create A Draft Quote As
    ...    ${ASSISTANT_EMAIL}    ${customer_id}    ${type_id}    ${suffix}
    Append To List    ${CREATED_QUOTE_IDS}    ${quote}[id]

    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    Click    [data-testid="submit-quote-QA-${suffix}"]

    # The status change is the assistant's half of the contract, and it is
    # synchronous: the quote is stored before anything is published.
    Quote Status Should Become    ${quote}[id]    pending-validation
    Sign Out

    # --- The manager is told --------------------------------------------
    Sign In As    ${MANAGER_EMAIL}
    # Waited for, not asserted: the notification arrives after a broker round
    # trip. This is the assertion that proves the publisher, the worker, the
    # notification store and the event stream are all wired together.
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Manager Should Have Been Notified About    QA-${suffix}

    # --- The manager validates ------------------------------------------
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tab-pending"]    visible
    Click    [data-testid="quote-tab-pending"]
    Wait For Elements State    [data-testid="validate-QA-${suffix}"]    visible
    Click    [data-testid="validate-QA-${suffix}"]

    # Validating issues the quote. It becomes SENT, not ACCEPTED — a manager
    # approving a price is not a customer agreeing to it.
    Quote Status Should Become    ${quote}[id]    sent
    Sign Out

    # --- The assistant is told the outcome ------------------------------
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Assistant Should Have Been Notified About    QA-${suffix}

A Refused Quote Comes Back To Its Author As A Draft
    [Documentation]    Refusal is not rejection, and the difference matters.
    ...
    ...    ``REJECTED`` means the *customer* declined. A manager sending a
    ...    quote back means the agency will not make that offer as written.
    ...    Collapsing the two would lose opposite facts about the same
    ...    customer, so a refused quote returns to ``draft`` and is editable
    ...    again.
    [Tags]    journey

    ${suffix}=    Unique Suffix
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type
    ${quote}=    Create A Draft Quote As
    ...    ${ASSISTANT_EMAIL}    ${customer_id}    ${type_id}    ${suffix}
    Append To List    ${CREATED_QUOTE_IDS}    ${quote}[id]
    Submit Quote Through The API    ${ASSISTANT_EMAIL}    ${quote}[id]

    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Click    [data-testid="quote-tab-pending"]
    Wait For Elements State    [data-testid="refuse-QA-${suffix}"]    visible
    Click    [data-testid="refuse-QA-${suffix}"]

    Quote Status Should Become    ${quote}[id]    draft
    Sign Out

An Assistant Cannot Reach The Manager Screens
    [Documentation]    The navigation hides what the role may not use.
    ...
    ...    A convenience rather than a control — the server refuses the request
    ...    regardless — but a screen an assistant can reach and that only shows
    ...    them errors is a bug report waiting to be filed.
    [Tags]    journey

    Sign In As    ${ASSISTANT_EMAIL}
    ${count}=    Get Element Count    [data-testid="nav--hcas"]
    Should Be Equal As Integers    ${count}    0
    ${map_count}=    Get Element Count    [data-testid="nav--map"]
    Should Be Equal As Integers    ${map_count}    0
    Sign Out

The Interface Switches Language Without Losing The Page
    [Documentation]    Both bundles are complete, and switching is not a reload.
    [Tags]    journey    i18n

    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Switch Language To    en
    Wait For Elements State    text=Quotes    visible
    Switch Language To    fr
    Wait For Elements State    text=Devis    visible
    Sign Out


*** Keywords ***
Prepare The Journey
    [Documentation]    Open the browser and start from a clean inbox.
    Clear The Mail Catcher
    Open The Application

Finish The Journey
    [Documentation]    Remove every quote this run created, then close up.
    ...
    ...    Exactly the ones this run made, by identifier — never "every quote
    ...    whose reference starts with QA". A teardown that deleted by pattern
    ...    would delete a concurrent run's fixtures too.
    Remove The Created Quotes
    Clear The Mail Catcher
    Close The Application

Remove The Created Quotes
    [Documentation]    Delete the campaign's own fixtures through the API.
    Remove The Quotes Created By This Run    @{CREATED_QUOTE_IDS}

Manager Should Have Been Notified About
    [Documentation]    Assert the manager's queue mentions a quote reference.
    [Arguments]    ${reference}
    ${notifications}=    Notifications Of    ${MANAGER_EMAIL}
    ${titles}=    Evaluate    [n["title"] for n in $notifications]
    ${joined}=    Catenate    @{titles}
    Should Contain    ${joined}    ${reference}

Assistant Should Have Been Notified About
    [Documentation]    Assert the author was told the outcome.
    [Arguments]    ${reference}
    ${notifications}=    Notifications Of    ${ASSISTANT_EMAIL}
    ${titles}=    Evaluate    [n["title"] for n in $notifications]
    ${joined}=    Catenate    @{titles}
    Should Contain    ${joined}    ${reference}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
