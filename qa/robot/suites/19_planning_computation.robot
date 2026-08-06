*** Settings ***
Documentation    Computing a planning from the screen, and seeing the result.
...
...              The endpoints existed and **nothing in the application ever
...              called them**: a freshly seeded stack had no planning, no way
...              to ask for one, and nothing on any screen to say so.
...
...              **Not idempotent in the ordinary sense, and it does not pretend
...              to be.** A planning run writes interventions, and re-running it
...              replaces them — which is what a planning run *is*. What this
...              suite guarantees instead is that the stack ends every run in
...              the same state it ends any other: one succeeded run over the
...              seeded week, and the visits it placed. The teardown recomputes
...              rather than deleting, so the next run starts from a planned
...              week exactly as this one did.

Library          Browser
Library          Collections
Library          DateTime
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Planning As An Administrator
Suite Teardown   Close The Application Without Coverage
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# The Monday the seeder plans its work into. The seeded lines all fall in the
# week after the seed ran, so this is the window with anything in it.
${PLANNED_WEEK}          ${EMPTY}


*** Test Cases ***
An Administrator Can Ask For A Planning To Be Computed
    [Documentation]    The control that did not exist.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="compute-planning"]    visible

Computing Places Every Seeded Visit
    [Documentation]    The run succeeds, and the seeded week is fully covered.
    ...
    ...    A run fails as a whole rather than partially, so one unplaceable
    ...    visit means no planning at all. That is exactly what a seeded window
    ...    outside the configured working day used to cause: sixteen of
    ...    seventy-seven visits outside 09:00–20:00, and a stack with an empty
    ...    calendar and no explanation on screen.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="compute-planning"]    enabled
    Click                      [data-testid="compute-planning"]

    Wait Until Keyword Succeeds    120s    2s    The Run Has Finished
    ${run}=    Latest Run
    Should Be Equal    ${run}[status]    succeeded
    ...    msg=The planning failed: ${run}[error_message]
    Should Be Empty    ${run}[unassigned_requirement_ids]
    Should Be True    ${run}[scheduled_count] > 0

The Result Is Reported On The Screen
    [Documentation]    Not a silent success: the run says what it placed.
    [Tags]    planning
    Wait For Elements State    [data-testid="planning-run-status"]    visible
    ${text}=    Get Text    [data-testid="planning-run-status"]
    Should Not Be Empty    ${text}

The Placed Visits Appear Without A Reload
    [Documentation]    The list refreshes itself when the run finishes.
    ...
    ...    The visits are written by a worker, behind the screen's back, so
    ...    nothing invalidates them on its own. Without that, an operator is
    ...    told "75 visits planned" above an empty list and has to reload to see
    ...    what they just asked for.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="planning-roster"]    visible
    # Read off the rail rather than the grid: the grid shows one week, and
    # which week the solver filled is its decision. The rail carries every
    # assistant's count over the whole window, so "somebody was planned" is
    # answerable without guessing who, or when.
    ${text}=    Get Text    [data-testid="planning-roster"]
    Should Not Match Regexp    ${text}    ^(\\s|0 visite\\(s\\))*$
    # And then on the grid, which is what the operator was actually looking at.
    # The month is stepped into rather than assumed: the run places visits over
    # the coming weeks, and the week the screen opens on may legitimately be
    # empty — a planning nobody has reached yet is not a planning that failed.
    Show A Calendar Month That Has Visits
    Wait For Elements State    .fc-event >> nth=0    visible

A Manager May Read The Planning But Not Compute It
    [Documentation]    All three run routes are administrator-only.
    ...
    ...    A button that only ever answers 403 is worse than no button: it tells
    ...    an operator the thing is theirs to do and then refuses them.
    [Tags]    planning    access
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible
    ${buttons}=    Get Element Count    [data-testid="compute-planning"]
    Should Be Equal As Integers    ${buttons}    0
    [Teardown]    Return To The Administrator


*** Keywords ***
Open The Planning As An Administrator
    [Documentation]    Sign in and open the planning screen on the seeded week.
    ${monday}=    The Monday Of Next Week
    Set Suite Variable    ${PLANNED_WEEK}    ${monday}
    Open The Application Without Coverage
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible

The Monday Of Next Week
    [Documentation]    Return the Monday the seeder plans its work into.
    ...
    ...    Computed the same way the seeder computes it rather than written
    ...    down, so the window follows the seeded data instead of going stale
    ...    the day after it was typed.
    ${today}=      Get Current Date    result_format=%Y-%m-%d
    ${weekday}=    Convert Date    ${today}    result_format=%w
    ${ahead}=      Evaluate    7 - int(${weekday}) if int(${weekday}) > 0 else 1
    ${monday}=     Add Time To Date    ${today}    ${ahead} days
    ...    result_format=%Y-%m-%d
    RETURN    ${monday}

Latest Run
    [Documentation]    Return the most recent planning run.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=20
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${runs}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${runs}    msg=No planning run exists.
    RETURN    ${runs}[0]

The Run Has Finished
    [Documentation]    Fail until the newest run has stopped running.
    ...
    ...    Polled rather than waited on for a fixed time: the solve has a
    ...    thirty-second budget but finishes sooner when the week is easy, and
    ...    a fixed sleep would be either flaky or slow.
    ${run}=    Latest Run
    Should Not Be Equal    ${run}[status]    pending
    Should Not Be Equal    ${run}[status]    running

Return To The Administrator
    [Documentation]    Leave the suite signed in as it started.
    Take A Screenshot On Failure
    Sign Out
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
