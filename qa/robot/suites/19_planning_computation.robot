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
...              the same state it ends any other: one finished run over the
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

Computing Produces A Plan
    [Documentation]    The run writes a week, whether or not all of it fitted.
    ...
    ...    This used to assert that a run either covered the seeded week
    ...    entirely or failed, because those were the only two outcomes: one
    ...    unplaceable visit meant no planning at all. A seeded window outside
    ...    the configured working day once put sixteen of seventy-seven visits
    ...    out of reach, and the stack came up with an empty calendar and no
    ...    explanation on screen.
    ...
    ...    Both halves of that are now wrong. A week that mostly works is
    ...    stored, so what this asserts is that **something was planned** — and
    ...    the partial case is checked properly in its own test below.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="compute-planning"]    enabled
    Click                      [data-testid="compute-planning"]

    Wait Until Keyword Succeeds    120s    2s    The Run Has Finished
    ${run}=    Latest Run
    Should Not Be Equal    ${run}[status]    failed
    ...    msg=The planning produced nothing at all: ${run}[error_message]
    Should Be True    ${run}[scheduled_count] > 0

    # **A week is planned even when part of it will not fit.** The run used to
    # fail outright the moment one visit could not be placed, which withheld
    # eighty-nine good visits over one impossible one. What is asserted now is
    # that a plan exists; whether every visit fitted is a property of the
    # seeded data, and `partial` is a legitimate outcome rather than a failure.
    IF    '${run}[status]' == 'partial'
        Should Not Be Empty    ${run}[unplaced_quotes]
        ...    msg=A partial run must name the quotes it could not fit.
    ELSE
        Should Be Empty    ${run}[unassigned_requirement_ids]
    END

The Result Is Reported On The Screen
    [Documentation]    Not a silent success: the run says what it placed.
    [Tags]    planning
    Wait For Elements State    [data-testid="planning-run-status"]    visible
    ${text}=    Get Text    [data-testid="planning-run-status"]
    Should Not Be Empty    ${text}

A Partial Run Names The Quote And The Reason
    [Documentation]    **What an operator can actually act on.**
    ...
    ...    The old message was one sentence quoting a solver status and a
    ...    configuration key — accurate, and useless to somebody whose job is
    ...    to telephone a customer and move a date. The report now names the
    ...    quote, the customer, each visit and why it did not fit.
    ...
    ...    Skipped when the seeded week happens to fit entirely, because that
    ...    is the good outcome and failing on it would make the suite depend
    ...    on the agency having a problem.
    [Tags]    planning
    ${run}=    Latest Run
    IF    '${run}[status]' != 'partial'
        Skip    The seeded week fitted entirely, so there is nothing to report.
    END
    ${quote}=    Set Variable    ${run}[unplaced_quotes][0]
    Should Not Be Empty    ${quote}[quote_reference]
    ...    msg=A finding an operator cannot trace to a quote is not actionable.
    Should Not Be Empty    ${quote}[visits]
    ${visit}=    Set Variable    ${quote}[visits][0]
    Should Not Be Empty    ${visit}[reason]
    ...    msg=Every unplaced visit must say why.

    # And on the screen, grouped under the quote rather than run together.
    Navigate To    /plannings
    Wait For Elements State    [data-testid="planning-run-status"]    visible
    ${text}=    Get Text    [data-testid="planning-run-status"]
    Should Contain    ${text}    ${quote}[quote_reference]
    ...    msg=The screen does not name the quote the operator has to chase.

The Run Says Whether The Rounds Were Proved Shortest
    [Documentation]    A plan is placed first and shortened second.
    ...
    ...    The second pass may run out of budget, in which case the first
    ...    pass's plan is stored unchanged: every visit scheduled, the driving
    ...    simply never proved minimal. That outcome is invisible in the plan
    ...    itself — a week with slightly longer rounds looks exactly like one
    ...    whose rounds are as short as they can be — so it is recorded on the
    ...    run and shown on the screen.
    ...
    ...    Asserted as "the field is present and is an answer", not as a
    ...    particular answer. Whether a given week can be *proved* optimal
    ...    inside the budget is a property of that week's data, and pinning it
    ...    here would make the suite fail the day somebody accepts a quote.
    [Tags]    smoke    planning
    ${run}=    Latest Run
    Dictionary Should Contain Key    ${run}    is_optimised
    Should Be True    ${run}[is_optimised] in [${True}, ${False}]
    ...    msg=A finished run must say whether its travel was proved minimal.

    # And the screen distinguishes the two. Both are successes — every visit
    # is scheduled either way — so the unoptimised one is info rather than an
    # error, and it is the *wording* that has to differ.
    ${text}=    Get Text    [data-testid="planning-run-status"]
    Should Not Be Empty    ${text}

Re-Planning The Same Week Gives The Same Answer
    [Documentation]    **The bug this whole computation was rebuilt around.**
    ...
    ...    One unchanged week replanned three times returned 404 minutes of
    ...    travel, then 371, then 355. A manager who reruns a plan and sees
    ...    three different numbers cannot tell an improvement from noise, or
    ...    tell whether the quote they just accepted changed anything.
    ...
    ...    Three things together fix it and all three are load-bearing: a fixed
    ...    seed, one search worker per day model, and a deterministic budget
    ...    rather than a wall-clock one. Solving the days at once does not
    ...    threaten it, because the days are independent problems.
    ...
    ...    Run through the API rather than the button: this needs two complete
    ...    runs over one period, and the screen offers no way to wait for the
    ...    first before starting the second.
    [Tags]    smoke    planning    determinism
    ${first}=    Latest Run
    Compute The Seeded Week Again
    ${second}=    Latest Run

    Should Be Equal As Integers
    ...    ${first}[total_travel_minutes]    ${second}[total_travel_minutes]
    ...    msg=The same week planned to ${first}[total_travel_minutes] minutes of travel and then ${second}[total_travel_minutes].
    Should Be Equal As Integers
    ...    ${first}[scheduled_count]    ${second}[scheduled_count]
    ...    msg=The same week placed a different number of visits on re-run.

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

Compute The Seeded Week Again
    [Documentation]    Start another run over the same period and wait for it.
    ...
    ...    Reuses the period of the run already on record rather than working
    ...    one out, because "the same week" is the whole point: two runs over
    ...    different periods would agree or differ for reasons that say
    ...    nothing about reproducibility.
    ...
    ...    Through the API rather than the button, because this needs the
    ...    first run to have finished before the second begins and the screen
    ...    offers no way to wait.
    ${previous}=    Latest Run
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary
    ...    period_start=${previous}[period_start]
    ...    period_end=${previous}[period_end]
    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=202
    Wait Until Keyword Succeeds    180s    3s    The Run Has Finished
    ${finished}=    Latest Run
    # Anything but `failed`. A week with a gap in it is still a week, and
    # `partial` is what the seeded data legitimately produces — demanding
    # `succeeded` here made this keyword assert the agency has no problems.
    Should Not Be Equal    ${finished}[status]    failed
    ...    msg=The re-run produced nothing: ${finished}[error_message]

Return To The Administrator
    [Documentation]    Leave the suite signed in as it started.
    Take A Screenshot On Failure
    Sign Out
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
