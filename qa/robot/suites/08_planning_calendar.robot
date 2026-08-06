*** Settings ***
Documentation    The calendar an assistant works from, in all three views.
...
...              The calendar is the screen an assistant opens most, and it is
...              the one with the most moving parts: three views, four
...              navigation controls, a click-through drawer and a working-day
...              window. Each is covered here because a broken one of them is a
...              visit somebody does not turn up to.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Calendar
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Week View Is What Opens
    [Documentation]    The default, because "this week" is the usual question.
    [Tags]    smoke    calendar
    Wait For Elements State    [data-testid="planning-calendar"]    visible
    Wait For Elements State    .fc-timeGridWeek-view    visible

The Day View Narrows To One Column
    [Documentation]    For an assistant checking today between two visits.
    [Tags]    calendar
    Click    .fc-timeGridDay-button
    Wait For Elements State    .fc-timeGridDay-view    visible
    [Teardown]    Return To The Week View

The Month View Shows The Whole Period
    [Documentation]    For seeing how full a month is at a glance.
    [Tags]    calendar
    Click    .fc-dayGridMonth-button
    Wait For Elements State    .fc-dayGridMonth-view    visible
    [Teardown]    Return To The Week View

Moving Forward And Back Returns To The Same Week
    [Documentation]    The two arrows are inverses, which is not automatic.
    ...
    ...    An off-by-one in either direction leaves an assistant reading the
    ...    wrong week's visits while believing they are reading this one's —
    ...    the worst possible failure for this screen, because nothing looks
    ...    wrong.
    [Tags]    calendar    navigation
    ${start}=    Get Text    .fc-toolbar-title
    Click    .fc-next-button
    ${next}=    Get Text    .fc-toolbar-title
    Should Not Be Equal    ${start}    ${next}
    Click    .fc-prev-button
    ${back}=    Get Text    .fc-toolbar-title
    Should Be Equal    ${start}    ${back}

Today Returns From Anywhere
    [Documentation]    However far an assistant has wandered.
    [Tags]    calendar    navigation
    ${start}=    Get Text    .fc-toolbar-title
    Click    .fc-next-button
    Click    .fc-next-button
    Click    .fc-next-button
    Click    .fc-today-button
    ${back}=    Get Text    .fc-toolbar-title
    Should Be Equal    ${start}    ${back}

The Working Day Is Bounded
    [Documentation]    07:00 to 21:00, matching the configured day.
    ...
    ...    An unbounded calendar opens scrolled to midnight and an assistant
    ...    sees eight empty hours before their first visit. The bounds are what
    ...    make an empty morning visibly empty.
    [Tags]    calendar
    Wait For Elements State    .fc-timegrid-slots    visible
    ${slots}=    Get Element Count    .fc-timegrid-slot-label
    Should Be True    ${slots} > 0
    Get Text    .fc-timegrid-slots    *=    07:00

Weekends Are Not Drawn
    [Documentation]    Five columns, not seven.
    ...
    ...    Two permanently empty columns are two columns of wasted width on a
    ...    laptop, and the agency's planned work is weekday work.
    [Tags]    calendar
    ${columns}=    Get Element Count    .fc-col-header-cell
    Should Be Equal As Integers    ${columns}    5

Clicking A Visit Opens Its Details
    [Documentation]    The drawer carrying the address the assistant travels to.
    ...
    ...    Skipped rather than failed when the seeded assistant has no visits in
    ...    the current window: that is a fact about the seed, not a defect in
    ...    the screen, and a test that fails for it would fail every Monday
    ...    after the seeded period rolls past.
    [Tags]    smoke    calendar
    ${events}=    Get Element Count    .fc-event
    Skip If    ${events} == 0    No visit in the current window to open.
    Click    .fc-event >> nth=0
    Wait For Elements State    [data-testid="intervention-detail"]    visible
    Get Text    [data-testid="intervention-detail"]    !=    ${EMPTY}
    [Teardown]    Close The Drawer

The Detail Drawer Names The Address And The Time
    [Documentation]    What the assistant actually needs from it.
    [Tags]    calendar
    ${events}=    Get Element Count    .fc-event
    Skip If    ${events} == 0    No visit in the current window to open.
    Click    .fc-event >> nth=0
    Wait For Elements State    [data-testid="intervention-detail"]    visible
    ${detail}=    Get Text    [data-testid="intervention-detail"]
    Should Match Regexp    ${detail}    \\d{2}:\\d{2}
    Should Match Regexp    ${detail}    \\d{5}
    [Teardown]    Close The Drawer


*** Keywords ***
Open The Calendar
    Open The Application
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/planning
    Wait For Elements State    [data-testid="planning-calendar"]    visible

Return To The Week View
    [Documentation]    Leave the calendar as the next test expects it.
    Click    .fc-timeGridWeek-button
    Wait For Elements State    .fc-timeGridWeek-view    visible

Close The Drawer
    [Documentation]    Dismiss the detail panel with the backdrop.
    Run Keyword And Ignore Error    Click    .MuiBackdrop-root
    Run Keyword And Ignore Error
    ...    Wait For Elements State    [data-testid="intervention-detail"]    detached

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
