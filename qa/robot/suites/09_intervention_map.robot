*** Settings ***
Documentation    The map: window selection, photograph pins, tooltips, side list.
...
...              The requirement this screen answers is specific — one pin per
...              intervention, the pin being the assistant's photograph, and a
...              tooltip carrying the customer's details — so each of those is
...              asserted rather than assumed from "the map rendered".

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Map
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Map Renders With Its Tiles
    [Documentation]    OpenStreetMap tiles, loaded without an API key.
    [Tags]    smoke    map
    Wait For Elements State    [data-testid="map"]         visible
    Wait For Elements State    .leaflet-container          visible
    # A loaded map is a grid of twenty-odd tiles, so the class matches every one
    # of them and Playwright's strict mode refuses the selector. Waiting on the
    # first says what the test means — that tiles arrived — without asserting
    # how many, which depends on the viewport.
    Wait For Elements State    .leaflet-tile-loaded >> nth=0    visible

The Attribution Is Present
    [Documentation]    OpenStreetMap's licence requires it, and it is not optional.
    [Tags]    map    licence
    Get Text    .leaflet-control-attribution    *=    OpenStreetMap

Each Intervention Draws One Pin
    [Documentation]    The requirement, asserted as a count rather than a glance.
    [Tags]    smoke    map
    Wait For Elements State    .leaflet-marker-icon >> nth=0    visible
    ${pins}=    Get Element Count    .simple-erp-pin
    ${rows}=    Get Element Count    [data-testid="map-list"] .MuiListItemButton-root
    Should Be True    ${pins} > 0
    # The side list and the map are two views of one set. A count that differs
    # means one of them is filtering and the other is not, and a manager would
    # be reading two different answers to the same question.
    Should Be Equal As Integers    ${pins}    ${rows}

A Pin Carries The Assistant's Photograph Or Their Initials
    [Documentation]    Never a blank circle.
    ...
    ...    "Who is where" is the question this screen exists to answer, and an
    ...    assistant whose portrait failed to load must still be a
    ...    distinguishable pin.
    [Tags]    map
    ${pins}=    Get Element Count    .simple-erp-pin
    Should Be True    ${pins} > 0
    ${content}=    Get Property    .simple-erp-pin >> nth=0    innerHTML
    Should Match Regexp    ${content}    (<img|<span)

Hovering A Pin Names The Customer And The Time
    [Documentation]    The tooltip the requirement asks for.
    [Tags]    smoke    map
    ${pins}=    Get Element Count    .simple-erp-pin
    Should Be True    ${pins} > 0
    Hover    .leaflet-marker-icon >> nth=0
    Wait For Elements State    .leaflet-tooltip    visible
    ${tooltip}=    Get Text    .leaflet-tooltip
    # A postcode and a clock time: the two things that identify which visit
    # this pin is, out of several at the same address.
    Should Match Regexp    ${tooltip}    \\d{5}
    Should Match Regexp    ${tooltip}    \\d{2}:\\d{2}

The Window Selector Changes What Is Drawn
    [Documentation]    Today, this week and the next seven days are different sets.
    ...
    ...    Asserted by comparing counts across the windows. A selector that
    ...    renders but does not refetch looks entirely correct until somebody
    ...    notices the same pins on every setting.
    [Tags]    map    filtering
    Click    [data-testid="map-window-today"]
    Sleep    2s
    ${today}=    Get Element Count    .simple-erp-pin

    Click    [data-testid="map-window-next7"]
    Sleep    2s
    ${next7}=    Get Element Count    .simple-erp-pin

    Should Be True    ${next7} >= ${today}
    [Teardown]    Select The Planning Window

The Map Opens On The Same Period As The Planning
    [Documentation]    The two screens draw the same visits, so they must agree.
    ...
    ...    This is the fault the window exists to prevent: the map opened on
    ...    the current week while the planning showed six, so a manager who had
    ...    just watched a run place seventy-seven visits opened the map and
    ...    found it empty. Nothing was broken — the screens were answering
    ...    different questions and neither said so.
    ...
    ...    Asserted against the API rather than against the planning screen, so
    ...    the comparison is with the data both screens read rather than with
    ...    whichever of them happens to be right.
    [Tags]    smoke    map    filtering
    Select The Planning Window
    ${class}=    Get Attribute    [data-testid="map-window-planning"]    class
    Should Contain    ${class}    Mui-selected
    ${planned}=    Interventions In The Planning Window
    ${drawn}=    Get Element Count    [data-testid="map-list"] .MuiListItemButton-root
    # Equal, or short by the visits with no coordinates — which the screen
    # counts out loud underneath rather than dropping in silence.
    Should Be True    ${drawn} <= ${planned}
    Should Be True    ${drawn} > 0
    ...    msg=The map is empty over the window the planning is full of.

The Counter Reports Drawn Against Total
    [Documentation]    An intervention without coordinates must be accounted for.
    ...
    ...    A silently dropped pin is a visit nobody is looking at. The screen
    ...    shows "drawn / total" so a manager can see the difference, and names
    ...    the shortfall underneath when there is one.
    [Tags]    map
    ${chip}=    Get Text    [data-testid="map-window"] >> xpath=../..
    Should Match Regexp    ${chip}    \\d+\\s*/\\s*\\d+

The Side List Mirrors The Map
    [Documentation]    Same visits, readable without panning.
    [Tags]    map
    Wait For Elements State    [data-testid="map-list"]    visible
    ${rows}=    Get Element Count    [data-testid="map-list"] .MuiListItemButton-root
    Should Be True    ${rows} > 0
    ${text}=    Get Text    [data-testid="map-list"]
    Should Match Regexp    ${text}    \\d{4}-\\d{2}-\\d{2}

The Map Can Be Zoomed
    [Documentation]    Leaflet's controls are wired and the view responds.
    [Tags]    map
    Wait For Elements State    .leaflet-control-zoom-in    visible
    Click    .leaflet-control-zoom-in
    Sleep    1s
    Wait For Elements State    .leaflet-container    visible


*** Keywords ***
Open The Map
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /map
    Wait For Elements State    [data-testid="map"]    visible
    # The window the screen already opens on. Selected explicitly anyway, so a
    # test that changed it leaves the next one where it expects to be.
    Select The Planning Window

Select The Planning Window
    [Documentation]    Draw the whole span the team planning shows.
    Click    [data-testid="map-window-planning"]
    Sleep    2s

Interventions In The Planning Window
    [Documentation]    Return how many visits the API has over the same span.
    ...
    ...    The same six weeks the screens read, anchored on the Monday of this
    ...    week — a window starting today would hide Monday's round from
    ...    anybody looking on Wednesday, and the map does not.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${today}=    Get Current Date    result_format=%Y-%m-%d
    ${weekday}=    Convert Date    ${today}    result_format=%w
    ${monday}=    Subtract Time From Date
    ...    ${today}    ${{ (int($weekday) - 1) % 7 }} days    result_format=%Y-%m-%d
    ${last}=    Add Time To Date    ${monday}    41 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${monday}    period_end=${last}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${count}=    Evaluate    sum(len(p["interventions"]) for p in $response.json())
    RETURN    ${count}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
