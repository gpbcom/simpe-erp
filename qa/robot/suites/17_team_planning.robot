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
    ...    Fewer than two assistants have work in the window. Nothing to merge.
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
    ...    Fewer than two assistants have work in the window. Nothing to hide.
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

A Manager Chooses Which Planning To Read
    [Documentation]    **One screen, two lenses, and the switch says which.**
    ...
    ...    The same visits group two ways: by who delivers the care, and by who
    ...    receives it. Neither is a filter over the other's answer, so the
    ...    control names both states rather than being a checkbox whose
    ...    unchecked half nobody can read off the screen.
    [Tags]    planning    audience
    Wait For Elements State    [data-testid="planning-audience"]    visible
    ...    message=A manager is offered no choice of planning.
    ${assistants}=    Get Element Count    [data-testid^="planning-hca-"]
    Should Be True    ${assistants} > 0
    ...    msg=The screen did not open on the assistants.

Switching To The Households Swaps The Rail
    [Documentation]    The rail answers "whose week am I reading".
    ...
    ...    Asserted on the rail rather than on the grid: the calendar draws the
    ...    same visits either way, so a switch that changed nothing but the
    ...    colours would still look as though it had worked.
    [Tags]    planning    audience
    Show The Households
    ${households}=    Get Element Count    [data-testid^="planning-customer-"]
    Should Be True    ${households} > 0
    ...    msg=The households lens listed nobody.
    ${assistants}=    Get Element Count    [data-testid^="planning-hca-"]
    Should Be Equal As Integers    ${assistants}    0
    ...    msg=The assistants are still in the rail after switching.
    [Teardown]    Show The Assistants

A Household's Visit Cannot Be Edited From Here
    [Documentation]    **The read-only claim, walked.**
    ...
    ...    Retyping a visit reprices the quote it came from and cancelling it
    ...    takes it off the customer's bill. Both belong to the assistants lens,
    ...    where a manager arrived to schedule rather than to answer a family's
    ...    question. A drawer that rendered the controls and ignored them would
    ...    look entirely right until somebody pressed one.
    [Tags]    planning    audience
    Show The Households
    Open The First Visit
    ${selector}=    Get Element Count    [data-testid="intervention-type-select"]
    Should Be Equal As Integers    ${selector}    0
    ...    msg=The households lens offers a service change. It is read-only.
    ${delete}=    Get Element Count    [data-testid="delete-intervention"]
    Should Be Equal As Integers    ${delete}    0
    ...    msg=The households lens offers a delete. It is read-only.
    [Teardown]    Close The Drawer And Show The Assistants

An Assistant Reaches Only The Households Planning
    [Documentation]    **Requirement and privacy rule in one test.**
    ...
    ...    The screen is now theirs to open — the households they visit are
    ...    exactly the ones they need a week of. What they must not get is the
    ...    workforce: an assistant has no business reading a colleague's diary,
    ...    and a switch whose other side answers 403 would be a control that
    ...    lies about what it does.
    [Tags]    planning    access    audience
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    ${entries}=    Get Element Count    [data-testid="nav--plannings"]
    Should Be Equal As Integers    ${entries}    1
    ...    msg=The plannings screen is no longer offered to an assistant.
    Navigate To    /plannings
    Wait For Elements State    [data-testid="team-planning-calendar"]    visible
    ...    message=An assistant was redirected away from the plannings screen.
    ${switch}=    Get Element Count    [data-testid="planning-audience"]
    Should Be Equal As Integers    ${switch}    0
    ...    msg=An assistant is offered a lens they may not read.
    ${assistants}=    Get Element Count    [data-testid^="planning-hca-"]
    Should Be Equal As Integers    ${assistants}    0
    ...    msg=An assistant can see the workforce rail.
    [Teardown]    Return To The Manager

An Assistant Sees Fewer Households Than A Manager
    [Documentation]    **The portfolio scoping, asserted as a number.**
    ...
    ...    An assistant sees the households they visit, union those they quoted
    ...    — not the agency's book. Read over the API rather than by counting
    ...    rail entries: the assertion is about what the server is willing to
    ...    hand over, and a rail is only what a screen chose to draw.
    [Tags]    planning    access    audience
    ${theirs}=    Households Readable By    ${ASSISTANT_EMAIL}
    ${everybody}=    Households Readable By    ${MANAGER_EMAIL}
    ${extra}=    Evaluate    sorted(set($theirs) - set($everybody))
    Should Be Empty    ${extra}
    ...    msg=An assistant can read households the manager cannot: ${extra}.
    Should Be True    len($theirs) <= len($everybody)
    ...    msg=An assistant reads ${theirs} households, a manager ${everybody}.


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

Show The Households
    [Documentation]    Switch the screen to the households lens and wait for it.
    ...
    ...    Waits for a rail entry rather than for the segment to look pressed:
    ...    the dataset arrives over the network, and a test that carried on
    ...    would read the previous lens's rail.
    Click    [data-testid="planning-audience-customers"]
    Wait For Elements State    [data-testid^="planning-customer-"] >> nth=0    visible
    ...    message=The households lens never populated its rail.

Show The Assistants
    [Documentation]    Switch the screen back to the assistants lens.
    Click    [data-testid="planning-audience-assistants"]
    Wait For Elements State    [data-testid^="planning-hca-"] >> nth=0    visible
    ...    message=The assistants lens never populated its rail.

Close The Drawer And Show The Assistants
    [Documentation]    Leave the screen on the lens the other tests expect.
    Run Keyword And Ignore Error    Keyboard Key    press    Escape
    Run Keyword And Ignore Error    Show The Assistants

Households Readable By
    [Documentation]    Return the household identifiers an account may read.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${today}=    Get Current Date    result_format=%Y-%m-%d
    ${later}=    Add Time To Date    ${today}    41 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${today}    period_end=${later}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/customers
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${identifiers}=    Evaluate    sorted(p["customer_id"] for p in $response.json())
    RETURN    ${identifiers}

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
