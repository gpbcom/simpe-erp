*** Settings ***
Documentation    When work may happen, and which days each assistant works.
...
...              Two screens that between them decide what the planner is
...              allowed to do. The agency's *hours* — the working day, the
...              midday break, the intervention radius — are one stored row a
...              manager owns. Each assistant's *days* are their own standing
...              arrangement, set by them and visible to their manager.
...
...              Both used to be out of reach. The hours lived in ``app.yaml``,
...              so moving the day to 08:00 meant a deployment. The days did
...              not exist at all, so "I never work Wednesdays" had to be filed
...              as one absence per Wednesday, forever. The tests here are
...              written against that: each one asserts a value reaching the
...              *server*, not merely a field accepting a keystroke.
...
...              **Idempotent by construction.** The planning rules are a
...              seeded singleton that cannot be created, so they are
...              snapshotted before anything runs and written back in a
...              teardown that fires even when the test that changed them
...              failed. The assistant's working week is restored the same way.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Snapshot The Rules And Open
Suite Teardown   Restore The Rules And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${ORIGINAL_SETTINGS}    ${EMPTY}
${ORIGINAL_WEEK}        ${EMPTY}
${ASSISTANT_HCA_ID}     ${EMPTY}


*** Test Cases ***
The Planning Rules Are Reachable From The Navigation
    [Documentation]    A screen with no door into it is a screen nobody finds.
    ...
    ...    The key ``nav.planningSettings`` existed in both bundles for some
    ...    time with no route behind it, so this walks the entry rather than
    ...    typing the address.
    [Tags]    smoke    navigation    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="nav--planning-settings"]    visible
    ...    message=The planning rules have no navigation entry.
    Click    [data-testid="nav--planning-settings"]
    Wait For Elements State    [data-testid="planning-settings-page"]    visible
    [Teardown]    Sign Out

The Screen Says A Change Does Not Re-Plan Anything
    [Documentation]    **The expectation that would otherwise be discovered.**
    ...
    ...    Saving new rules does not recompute this week — doing so would move
    ...    assistants who have already been told where to go. A manager
    ...    widening a radius to fix today's gap and finding nothing changed has
    ...    been misled unless the screen said so first.
    [Tags]    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Wait For Elements State    [data-testid="planning-settings-notice"]    visible
    [Teardown]    Sign Out

The Working Day Is Loaded From The Server
    [Documentation]    Minutes on the wire, a clock time in the field.
    ...
    ...    The API publishes ``540``, the input needs ``09:00``. A conversion
    ...    that silently produced ``9:0`` or an empty field would leave the
    ...    form looking blank rather than wrong.
    [Tags]    smoke    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    ${start}=    Get Property    [data-testid="day-start"]    value
    Should Match Regexp    ${start}    ^\\d{2}:\\d{2}$
    ...    msg=The working day started at '${start}', which is not a clock time.
    [Teardown]    Sign Out

A Manager Moves The Working Day And The Server Keeps It
    [Documentation]    **The whole point of the feature.**
    ...
    ...    This value used to come from a configuration file, so changing it
    ...    was a deployment. The assertion is against the API rather than the
    ...    field, because a form that keeps a typed value and never sends it
    ...    looks identical to one that works.
    [Tags]    smoke    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Fill Text    [data-testid="day-start"]    08:00
    Fill Text    [data-testid="day-end"]      19:30
    Click    [data-testid="planning-settings-save"]
    Wait For Elements State    [data-testid="planning-settings-saved"]    visible

    ${stored}=    Planning Rules As Stored
    Should Be Equal As Integers    ${stored}[day_start_minute]    480
    Should Be Equal As Integers    ${stored}[day_end_minute]      1170
    [Teardown]    Restore The Rules And Sign Out

A Manager Moves The Lunch Window And The Server Keeps It
    [Documentation]    The break's length and its window are both configurable.
    ...
    ...    The length was already stored. The window was not, so a manager
    ...    could lengthen the break but not say when it might fall.
    [Tags]    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Fill Text    [data-testid="lunch-minutes"]    90
    Fill Text    [data-testid="lunch-start"]      12:00
    Fill Text    [data-testid="lunch-end"]        14:00
    Click    [data-testid="planning-settings-save"]
    Wait For Elements State    [data-testid="planning-settings-saved"]    visible

    ${stored}=    Planning Rules As Stored
    Should Be Equal As Integers    ${stored}[lunch_break_minutes]           90
    Should Be Equal As Integers    ${stored}[lunch_window_start_minute]     720
    Should Be Equal As Integers    ${stored}[lunch_window_end_minute]       840
    [Teardown]    Restore The Rules And Sign Out

A Day That Ends Before It Starts Cannot Be Saved
    [Documentation]    Two plausible numbers that are only wrong together.
    ...
    ...    Caught on the screen it names the conflicting pair. Reaching the
    ...    solver it is a planning run that fails against every visit with "no
    ...    feasible slot", which names nothing anybody can act on.
    [Tags]    smoke    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Fill Text    [data-testid="day-start"]    20:00
    Fill Text    [data-testid="day-end"]      09:00
    Wait For Elements State    [data-testid="planning-settings-problem"]    visible
    Get Element States    [data-testid="planning-settings-save"]    contains    disabled
    [Teardown]    Reload And Sign Out

A Lunch Window Outside The Working Day Cannot Be Saved
    [Documentation]    A break nobody could take is refused before the request.
    [Tags]    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Fill Text    [data-testid="day-start"]    10:00
    Fill Text    [data-testid="day-end"]      18:00
    Fill Text    [data-testid="lunch-start"]  09:00
    Fill Text    [data-testid="lunch-end"]    11:00
    Wait For Elements State    [data-testid="planning-settings-problem"]    visible
    Get Element States    [data-testid="planning-settings-save"]    contains    disabled
    [Teardown]    Reload And Sign Out

A Lunch Window Too Narrow For The Break Cannot Be Saved
    [Documentation]    A 60-minute window cannot hold a 90-minute break.
    ...
    ...    The pair the two individual fields both accept. Neither number is
    ...    out of range on its own, which is what makes the cross-field check
    ...    the only thing standing between them and an infeasible week.
    [Tags]    planning-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Planning Rules
    Fill Text    [data-testid="lunch-minutes"]    90
    Fill Text    [data-testid="lunch-start"]      12:00
    Fill Text    [data-testid="lunch-end"]        13:00
    Wait For Elements State    [data-testid="planning-settings-problem"]    visible
    Get Element States    [data-testid="planning-settings-save"]    contains    disabled
    [Teardown]    Reload And Sign Out

The Server Refuses An Unworkable Day Sent By Hand
    [Documentation]    The screen's check is a courtesy. This is the control.
    ...
    ...    Sent past the form entirely, because a disabled button guards only
    ...    the people using the button.
    [Tags]    smoke    planning-settings    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    max_intervention_radius_km=${30.0}
    ...    day_start_minute=${1200}
    ...    day_end_minute=${540}
    ...    lunch_break_minutes=${60}
    ...    lunch_window_start_minute=${690}
    ...    lunch_window_end_minute=${870}
    PUT
    ...    ${API_URL}/api/v1/planning/settings
    ...    json=${body}    headers=${headers}    expected_status=422

An Assistant Cannot Reach The Planning Rules
    [Documentation]    Who may work is not the same as when work may happen.
    ...
    ...    An assistant sets their own days. The agency's hours are a manager's
    ...    decision. Asserted on where they *do* land, because waiting for a
    ...    screen that is expected never to appear proves nothing until the
    ...    timeout expires.
    [Tags]    smoke    planning-settings    access
    Sign In As    ${ASSISTANT_EMAIL}
    Go To    ${BASE_URL}/planning-settings
    Wait For Elements State    [data-testid="account-section"]    visible
    ${reached}=    Get Element Count    [data-testid="planning-settings-page"]
    Should Be Equal As Integers    ${reached}    0
    ...    msg=An assistant reached the planning rules by typing the address.
    [Teardown]    Sign Out

The Server Refuses An Assistant Reading The Planning Rules
    [Documentation]    Sent by hand, because the screen offers no way to.
    [Tags]    smoke    planning-settings    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    GET    ${API_URL}/api/v1/planning/settings    headers=${headers}
    ...    expected_status=403

An Assistant Sees Their Own Working Week
    [Documentation]    Seven days, each one on or off.
    [Tags]    smoke    working-days
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="working-days-section"]    visible
    ${chips}=    Get Element Count    css=[data-testid^="working-day-"]
    Should Be True    ${chips} >= 7
    ...    msg=The working week showed ${chips} days rather than seven.
    [Teardown]    Sign Out

An Assistant Drops A Day And The Server Keeps It
    [Documentation]    **"I never work Wednesdays", said once.**
    ...
    ...    Before this existed the only way to say it was one absence per
    ...    Wednesday, filed forever. Asserted against the API, because the chip
    ...    turning grey proves only that the chip turned grey.
    [Tags]    smoke    working-days
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="working-day-wednesday"]    visible
    Click    [data-testid="working-day-wednesday"]
    Click    [data-testid="save-working-days"]
    Wait For Elements State    [data-testid="working-days-saved"]    visible

    ${stored}=    Working Week As Stored
    Should Not Contain    ${stored}    wednesday
    ...    msg=Wednesday survived a save that removed it.
    Should Contain    ${stored}    monday
    ...    msg=Removing Wednesday took Monday with it.
    [Teardown]    Restore The Week And Sign Out

A Week With No Working Day Cannot Be Saved
    [Documentation]    Clearing every box is a statement, not a reset request.
    ...
    ...    Its two readings — "I work no days" and "put me back on the
    ...    standard week" — are opposites, so the screen refuses rather than
    ...    guessing.
    [Tags]    smoke    working-days
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="working-day-list"]    visible
    Clear Every Working Day
    Wait For Elements State    [data-testid="working-days-empty"]    visible
    Get Element States    [data-testid="save-working-days"]    contains    disabled
    [Teardown]    Reload And Sign Out

The Server Refuses An Empty Week Sent By Hand
    [Documentation]    The disabled button guards only the button's users.
    [Tags]    working-days    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    working_weekdays=@{EMPTY}
    PUT
    ...    ${API_URL}/api/v1/hcas/${ASSISTANT_HCA_ID}/working-days
    ...    json=${body}    headers=${headers}    expected_status=422

An Assistant Cannot Set A Colleague's Working Week
    [Documentation]    **What stops one assistant taking another off the rota.**
    ...
    ...    Nothing at the routing layer stops assistant A putting assistant B's
    ...    identifier in the path; only the service can compare the two. Sent
    ...    by hand, because the screen offers no way to address a colleague.
    [Tags]    smoke    working-days    access
    ${colleague}=    Hca Id Of    ${OTHER_ASSISTANT}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    working_weekdays=${{ ["monday"] }}
    PUT
    ...    ${API_URL}/api/v1/hcas/${colleague}/working-days
    ...    json=${body}    headers=${headers}    expected_status=403

A Manager Sees Every Assistant's Working Week
    [Documentation]    Visible to a manager, which is half of what it is for.
    ...
    ...    An assistant declaring "no Wednesdays" that only they can see is a
    ...    rota nobody can plan around.
    [Tags]    smoke    working-days
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /hcas
    Wait For Elements State
    ...    css=[data-testid^="working-day-${ASSISTANT_HCA_ID}-"]    visible
    ${days}=    Get Element Count
    ...    css=[data-testid^="working-day-${ASSISTANT_HCA_ID}-"]
    Should Be Equal As Integers    ${days}    7
    ...    msg=The workforce grid showed ${days} days rather than seven.
    [Teardown]    Sign Out

A Manager Sets An Assistant's Working Week For Them
    [Documentation]    Recording that somebody dropped to four days is the job.
    ...
    ...    The same ownership check that refuses a colleague lets a manager
    ...    through — somebody who telephones to say they no longer work Fridays
    ...    should not have to sign in to record it.
    [Tags]    working-days    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    working_weekdays=${{ ["monday", "tuesday", "wednesday", "thursday"] }}
    ${response}=    PUT
    ...    ${API_URL}/api/v1/hcas/${ASSISTANT_HCA_ID}/working-days
    ...    json=${body}    headers=${headers}    expected_status=200
    Should Not Contain    ${response.json()}[working_weekdays]    friday
    [Teardown]    Restore The Week

The Stored Week Comes Back Ordered Monday First
    [Documentation]    Two spellings of one week must not read differently.
    ...
    ...    The set is stored as a delimited string, so an unsorted save would
    ...    produce two different rows for the same working week — and a screen
    ...    whose chips moved about between saves.
    [Tags]    working-days
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    working_weekdays=${{ ["friday", "monday", "wednesday"] }}
    ${response}=    PUT
    ...    ${API_URL}/api/v1/hcas/${ASSISTANT_HCA_ID}/working-days
    ...    json=${body}    headers=${headers}    expected_status=200
    Should Be Equal
    ...    ${response.json()}[working_weekdays]
    ...    ${{ ["monday", "wednesday", "friday"] }}
    [Teardown]    Restore The Week


*** Keywords ***
Snapshot The Rules And Open
    [Documentation]    Record the rules and the working week, then open up.
    ...
    ...    Both are seeded and cannot be created, so the only way this suite
    ...    stays runnable twice is to put back exactly what it found.
    ${settings}=    Planning Rules As Stored
    Set Suite Variable    ${ORIGINAL_SETTINGS}    ${settings}
    ${hca_id}=    Hca Id Of    ${ASSISTANT_EMAIL}
    Set Suite Variable    ${ASSISTANT_HCA_ID}    ${hca_id}
    ${week}=    Working Week As Stored
    Set Suite Variable    ${ORIGINAL_WEEK}    ${week}
    Open The Application

Restore The Rules And Close
    [Documentation]    Put both back, then close the browser.
    Run Keyword And Ignore Error    Restore The Rules
    Run Keyword And Ignore Error    Restore The Week
    Close The Application

Restore The Rules And Sign Out
    [Documentation]    Undo a test that changed the rules, then end the session.
    Run Keyword And Ignore Error    Restore The Rules
    Sign Out

Restore The Week And Sign Out
    [Documentation]    Undo a test that changed the week, then end the session.
    Run Keyword And Ignore Error    Restore The Week
    Sign Out

Reload And Sign Out
    [Documentation]    Discard an unsaved form, then end the session.
    Run Keyword And Ignore Error    Reload
    Sign Out

Open The Planning Rules
    [Documentation]    Follow the navigation entry and wait for the form.
    ...
    ...    Waits for a field rather than for the page, because the form is
    ...    populated from the query and a test that filled it before the
    ...    response arrived would have its keystrokes overwritten.
    Navigate To    /planning-settings
    Wait For Elements State    [data-testid="day-start"]    visible

Planning Rules As Stored
    [Documentation]    Read the rules as the server currently holds them.

    ...    Returns:
    ...        dict: The stored planning settings.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/settings
    ...    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Restore The Rules
    [Documentation]    Write the rules back exactly as the suite found them.
    Run Keyword And Return If    '${ORIGINAL_SETTINGS}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    max_intervention_radius_km=${ORIGINAL_SETTINGS}[max_intervention_radius_km]
    ...    day_start_minute=${ORIGINAL_SETTINGS}[day_start_minute]
    ...    day_end_minute=${ORIGINAL_SETTINGS}[day_end_minute]
    ...    lunch_break_minutes=${ORIGINAL_SETTINGS}[lunch_break_minutes]
    ...    lunch_window_start_minute=${ORIGINAL_SETTINGS}[lunch_window_start_minute]
    ...    lunch_window_end_minute=${ORIGINAL_SETTINGS}[lunch_window_end_minute]
    PUT
    ...    ${API_URL}/api/v1/planning/settings
    ...    json=${body}    headers=${headers}    expected_status=200

Hca Id Of
    [Documentation]    Return the assistant record bound to an account.

    ...    Arguments:
    ...        email: The account to sign in as.
    ...
    ...    Returns:
    ...        str: The assistant's identifier.
    ...
    ...    Read through ``/me/hca`` rather than by searching the workforce, so
    ...    the identifier comes from the credential and cannot point at
    ...    somebody else's record.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/hca    headers=${headers}    expected_status=200
    RETURN    ${response.json()}[id]

Working Week As Stored
    [Documentation]    Read the assistant's working week from the server.

    ...    Returns:
    ...        list: The weekday values, ordered Monday first.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/hca    headers=${headers}    expected_status=200
    RETURN    ${response.json()}[working_weekdays]

Restore The Week
    [Documentation]    Write the working week back as the suite found it.
    Run Keyword And Return If    '${ORIGINAL_WEEK}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    working_weekdays=${ORIGINAL_WEEK}
    PUT
    ...    ${API_URL}/api/v1/hcas/${ASSISTANT_HCA_ID}/working-days
    ...    json=${body}    headers=${headers}    expected_status=200

Take A Screenshot On Failure
    [Documentation]    Capture the screen a failing test left behind.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True

Clear Every Working Day
    [Documentation]    Untick every day that is currently ticked.
    ...
    ...    Driven off each chip's own ``data-selected`` rather than off a
    ...    known starting week: the seed may change, and a keyword that
    ...    clicked all seven unconditionally would *select* the ones that were
    ...    already off and leave the week half full.
    @{days}=    Create List
    ...    monday    tuesday    wednesday    thursday    friday    saturday    sunday
    FOR    ${day}    IN    @{days}
        ${state}=    Get Attribute    [data-testid="working-day-${day}"]    data-selected
        IF    '${state}' == 'true'
            Click    [data-testid="working-day-${day}"]
        END
    END
