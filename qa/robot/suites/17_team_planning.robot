*** Settings ***
Documentation    The assistants' planning as a calendar: everybody, or one of them.
...
...              A calendar rather than a list of cards: the question a manager
...              asks is "who is where at three o'clock on Thursday?", and rows
...              sorted by date answer it only after they have been counted.
...              The screen opens on the whole workforce; choosing a name from
...              the rail on the left narrows the grid to that assistant alone.
...
...              The narrowing is asserted in both directions — the shared grid
...              names several assistants, one assistant's grid names nobody
...              else — because a filter that renders but never filters looks
...              entirely right until a manager acts on somebody else's visit.
...
...              **Read-only, so idempotent for free.** This suite opens a
...              screen, picks people and reads. There is no fixture to remove
...              and nothing a second run starts from differently.

Library          Browser
Library          Collections
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Team Planning
Suite Teardown   Close The Application Without Coverage
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Screen Opens On A Calendar, Not A List
    [Documentation]    The grid a manager reads a week off.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible
    Wait For Elements State    .fc                                      visible

Everybody And Every Assistant Are Offered On The Left
    [Documentation]    The rail is how a planning is chosen.
    ...
    ...    The seeded agency has twelve assistants, so a rail with one entry is
    ...    as wrong as a rail with none — asserted as "more than one" rather
    ...    than an exact count, which would go stale the day the seed changes.
    [Tags]    smoke    planning
    Wait For Elements State    [data-testid="planning-roster"]    visible
    Wait For Elements State    [data-testid="planning-all"]       visible
    ${entries}=    Get Element Count    css=[data-testid^="planning-hca-"]
    Should Be True    ${entries} > 1    msg=The rail offers no choice.

The Screen Opens On The Whole Workforce
    [Documentation]    A manager lands on the overview, not on one person.
    ...
    ...    "Who is out this week" is what brings a manager here; opening on the
    ...    first assistant alphabetically would answer a question nobody asked
    ...    and hide the eleven others behind a click.
    [Tags]    smoke    planning
    ${class}=    Get Attribute    [data-testid="planning-all"]    class
    Should Contain    ${class}    Mui-selected
    ${narrowed}=    Get Element Count    css=[data-testid^="planning-hca-"].Mui-selected
    Should Be Equal As Integers    ${narrowed}    0

The Shared Grid Carries Several Assistants At Once
    [Documentation]    Everybody means everybody, not the first one found.
    ...
    ...    Counting blocks would not do: the grid draws one week of a six-week
    ...    window, so a count says nothing about whose visits they are. The
    ...    assertion is on the *names* the grid spells out, which is also what a
    ...    manager reads off it.
    [Tags]    smoke    planning
    Show Everybody
    Show A Calendar Month That Has Visits
    ${busy}=    Assistants With Visits
    Skip If    len($busy) < 2
    ...    Fewer than two assistants have work in the window; nothing to merge.
    ${named}=    Assistants Named In The Grid    ${busy}
    Should Be True    len($named) >= 2
    ...    msg=The shared grid names ${named}, so it is not showing everybody.

Choosing One Assistant Hides Everybody Else
    [Documentation]    The rail narrows the grid, which is the whole point of it.
    ...
    ...    Asserted as an absence as well as a presence. A grid that kept every
    ...    visit and merely moved the highlight would pass a test that only
    ...    checked the chosen assistant's own name was still there.
    [Tags]    smoke    planning
    ${busy}=    Assistants With Visits
    Skip If    len($busy) < 2
    ...    Fewer than two assistants have work in the window; nothing to hide.
    ${chosen}=    Set Variable    ${busy}[0]
    Click    [data-testid="planning-hca-${chosen}[id]"]
    Wait For Elements State
    ...    [data-testid="planning-hca-${chosen}[id]"].Mui-selected    attached
    Show A Calendar Month That Has Visits
    Wait For Elements State    .fc-event >> nth=0    visible
    ${named}=    Assistants Named In The Grid    ${busy}
    # The chosen assistant's own visits carry the customer's name rather than
    # theirs, so the grid naming *nobody* is the correct outcome here; what
    # matters is that no colleague of theirs is named.
    Should Be Empty    ${named}
    ...    msg=The grid still shows ${named} after narrowing to one assistant.
    [Teardown]    Show Everybody

A Visit Names Its Assistant, Its Customer And Its Address
    [Documentation]    The drawer a manager acts on.
    ...
    ...    The assistant's full name is asserted because on the shared grid the
    ...    block was told apart by its colour, and a colour is not something
    ...    anybody can act on: "who do I ring about this visit" has to be
    ...    answerable in words.
    [Tags]    smoke    planning
    ${busy}=    Assistants With Visits
    Skip If    len($busy) == 0
    ...    No assistant has a visit in the window; compute a planning first.
    ${chosen}=    Set Variable    ${busy}[0]
    Click    [data-testid="planning-hca-${chosen}[id]"]
    Show A Calendar Month That Has Visits
    Wait For Elements State    .fc-event >> nth=0    visible
    Click    .fc-event >> nth=0
    Wait For Elements State    [data-testid="team-intervention-detail"]    visible
    Get Text    [data-testid="team-intervention-hca"]    ==    ${chosen}[name]
    ${detail}=    Get Text    [data-testid="team-intervention-detail"]
    Should Match Regexp    ${detail}    \\d{5}
    [Teardown]    Close The Drawer And Show Everybody

A Visit Offers Both Of Its Edits
    [Documentation]    Re-classify it, or cancel it: the two things a manager does.
    ...
    ...    Only the presence of the controls is asserted here. Cancelling takes
    ...    the visit off the quote it was sold on and cannot be undone by
    ...    clicking anything, so it is exercised in the unit suite against a
    ...    fixture rather than against the seeded agency — a campaign that
    ...    deleted seeded work would pass once and fail on the second run.
    [Tags]    smoke    planning
    Open The First Visit
    Wait For Elements State    [data-testid="intervention-type-select"]    visible
    Wait For Elements State    [data-testid="delete-intervention"]         visible
    [Teardown]    Close The Drawer And Show Everybody

Cancelling Asks Before It Bills Anything Differently
    [Documentation]    The confirmation names what is about to go.
    ...
    ...    Opened and dismissed. What this covers is that the destructive path
    ...    is guarded and says what it will do — a manager who mis-clicks a
    ...    calendar block must not silently change a customer's bill.
    [Tags]    planning
    Open The First Visit
    Click    [data-testid="delete-intervention"]
    Wait For Elements State    [data-testid="delete-intervention-explain"]    visible
    ${text}=    Get Text    [data-testid="delete-intervention-explain"]
    Should Match Regexp    ${text}    \\d{4}-\\d{2}-\\d{2}
    Wait For Elements State    [data-testid="confirm-delete-intervention"]    visible
    Click    text=Annuler
    Wait For Elements State    [data-testid="delete-intervention-explain"]    detached
    [Teardown]    Close The Drawer And Show Everybody

The Service Selector Offers The Catalogue
    [Documentation]    Every sellable service, with the visit's own preselected.
    ...
    ...    Read rather than changed. Re-classifying a seeded visit reprices a
    ...    seeded quote, which the campaign treats as read-only; what the
    ...    repricing actually does is asserted in the unit suite, where the
    ...    figures can be checked rather than glanced at.
    [Tags]    planning
    Open The First Visit
    ${options}=    Get Element Count    [data-testid="intervention-type-select"] option
    Should Be True    ${options} > 1    msg=The selector offers no alternative.
    ${chosen}=    Get Selected Options
    ...    [data-testid="intervention-type-select"] select    label
    Should Not Be Empty    ${chosen}
    [Teardown]    Close The Drawer And Show Everybody

An Assistant Cannot Reach The Screen
    [Documentation]    It is about the workforce, not about oneself.
    ...
    ...    A convenience, not a control — the API refuses an assistant either
    ...    way. What this asserts is that the navigation does not offer a screen
    ...    that would only show them errors.
    [Tags]    planning    access
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    ${entries}=    Get Element Count    [data-testid="nav--plannings"]
    Should Be Equal As Integers    ${entries}    0
    [Teardown]    Return To The Manager


*** Keywords ***
Open The Team Planning
    [Documentation]    Sign in as a manager and open the screen.
    ...
    ...    The planning is a precondition here too. This suite degrades to
    ...    ``Skip If`` on an empty window, which is honest but useless: a
    ...    campaign where 17 silently skips proves nothing about the screen it
    ...    exists to cover.
    Ensure A Planning Has Been Computed
    Open The Application Without Coverage
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible

Show Everybody
    [Documentation]    Select the rail entry that draws the whole workforce.
    Click    [data-testid="planning-all"]
    Wait For Elements State    [data-testid="planning-all"].Mui-selected    attached

Open The First Visit
    [Documentation]    Open the detail drawer of a busy assistant's first visit.
    ...
    ...    Which of twelve people the solver gave work to is its decision, so
    ...    the assistant is asked for rather than assumed.
    ${busy}=    Assistants With Visits
    Skip If    len($busy) == 0
    ...    No assistant has a visit in the window; compute a planning first.
    Click    [data-testid="planning-hca-${busy}[0][id]"]
    Show A Calendar Month That Has Visits
    Wait For Elements State    .fc-event >> nth=0    visible
    Click    .fc-event >> nth=0
    Wait For Elements State    [data-testid="team-intervention-detail"]    visible

Close The Drawer And Show Everybody
    [Documentation]    Leave the screen as the next test expects to find it.
    Take A Screenshot On Failure
    Keyboard Key    press    Escape
    Wait For Elements State    [data-testid="team-intervention-detail"]    detached
    Show Everybody

Assistants With Visits
    [Documentation]    Return ``{id, name}`` for each assistant with work, or ``[]``.
    ...
    ...    Read through the API rather than by clicking every entry to see which
    ...    grid fills: twelve clicks to find one is twelve chances to be flaky.
    ...    Which of twelve people the solver gave work to is its decision, not
    ...    this suite's, so the tests ask rather than assume.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${today}=    Get Current Date    result_format=%Y-%m-%d
    ${later}=    Add Time To Date    ${today}    41 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${today}    period_end=${later}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    # One line: a ``...`` continuation is the *next argument*, not more of this
    # one, and Evaluate's second argument is the module list — which is how a
    # split expression reports itself as "No module named 'forpin$response'".
    ${busy}=    Evaluate    [{"id": p["hca_id"], "name": p["hca_full_name"]} for p in $response.json() if p["interventions"]]
    RETURN    ${busy}

Assistants Named In The Grid
    [Documentation]    Return which of ``${assistants}`` the calendar spells out.
    ...
    ...    Matched on the full name. A surname alone would collide with a
    ...    customer of the same family — which the seed has, because families
    ...    are exactly who an agency serves.
    [Arguments]    ${assistants}
    ${grid}=    Get Text    [data-testid="team-planning-calendar"]
    ${named}=    Evaluate    [a["name"] for a in $assistants if a["name"] in $grid]
    RETURN    ${named}

Return To The Manager
    [Documentation]    Leave the suite as it was found, signed in as a manager.
    Take A Screenshot On Failure
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
