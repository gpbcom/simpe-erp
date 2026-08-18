*** Settings ***
Documentation    Team scoping — what a manager sees now that the company has
...              more than one team, and what they are refused.
...
...              Before teams existed, a manager saw the whole agency: every
...              quote, every assistant, every household, every calendar. They
...              now see **the teams they run**, and an administrator still sees
...              everything.
...
...              This suite proves the narrowing **from both sides**, which is
...              the only way it means anything:
...
...              - the screens a manager opens really are narrowed, and
...              - the request a screen will not make is sent **by hand** and
...                answered 403 or 404.
...
...              The second half is the important one. A narrowing that lives
...              only in the interface is not a narrowing: it is a screen that
...              declines to show something the API will happily hand over to
...              anybody who types the URL.
...
...              The fixture is a **second team**, formed here and removed by
...              the teardown. The seed deliberately keeps every seeded person
...              and quote in one team so that every count the rest of the
...              campaign asserts is unchanged — so a suite that wants to watch
...              the narrowing bite has to make its own second team.

Library          Browser
Library          Collections
Library          DateTime
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Form A Second Team
Suite Teardown   Remove Every Fixture And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${QA_SITE}          ${EMPTY}
${QA_TEAM}          ${EMPTY}
${QA_SITE_ID}       ${EMPTY}
${QA_TEAM_ID}       ${EMPTY}
# The seeded team, which the second manager does *not* run.
${SEEDED_TEAM_ID}   ${EMPTY}


*** Test Cases ***
An Administrator Sees Every Team
    [Documentation]    ``None`` from the narrowing means every team, not no team.
    ...
    ...    The distinction between "unscoped" and "scoped to nothing" is the one
    ...    that opens a company if it is read the wrong way round, so both ends
    ...    of it are asserted — here, and in the test below.
    [Tags]    smoke    scoping
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams
    ...    headers=${headers}
    ...    expected_status=200
    Should Be True    ${{ len($response.json()) }} >= 2
    ...    msg=An administrator was not shown the whole company.

A Manager Sees Only The Teams They Run
    [Documentation]    **The narrowing, from the inside.**
    ...
    ...    The second manager runs the team this suite formed and nothing else,
    ...    so the seeded team must not appear. Asserted on the identifiers
    ...    rather than on a count, because a count that happens to match tells
    ...    you nothing about *which* rows came back.
    [Tags]    smoke    scoping
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams
    ...    headers=${headers}
    ...    expected_status=200
    ${ids}=    Evaluate    [team["id"] for team in $response.json()]
    Should Contain    ${ids}    ${QA_TEAM_ID}
    Should Not Contain    ${ids}    ${SEEDED_TEAM_ID}
    ...    msg=A manager was shown a team they do not run.

A Manager Sees Only Their Teams' Quotes
    [Documentation]    Every seeded quote belongs to the seeded team.
    ...
    ...    So the second manager's quote book must be empty — not because there
    ...    are no quotes, but because none of them are theirs. That is the
    ...    strongest form this assertion can take: the rows exist, are readable
    ...    by somebody else, and do not come back.
    [Tags]    smoke    scoping    quotes
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Empty    ${response.json()}
    ...    msg=A manager was shown quotes belonging to another team.

An Administrator Still Sees Every Quote
    [Documentation]    The other end of the same rule.
    ...
    ...    Without this, a narrowing that returned nothing to everybody would
    ...    pass the test above and break the whole application.
    [Tags]    smoke    scoping    quotes
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes
    ...    headers=${headers}
    ...    expected_status=200
    Should Not Be Empty    ${response.json()}
    ...    msg=The narrowing hid the seeded quote book from an administrator.

A Manager Sees Only Their Teams' Assistants
    [Documentation]    Every seeded assistant is on the seeded team.
    [Tags]    scoping    workforce
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Empty    ${response.json()}
    ...    msg=A manager was shown the workforce of another team.

A Manager Sees Only Their Teams' Households
    [Documentation]    The household scope is read off the quotes, not the calendar.
    ...
    ...    A prospect who has been quoted and never planned is still the
    ...    manager's business — but every seeded quote belongs to the seeded
    ...    team, so none of them is this manager's.
    [Tags]    scoping    customers
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Empty    ${response.json()}
    ...    msg=A manager was shown households served by another team.

A Manager Cannot Plan A Team They Do Not Run
    [Documentation]    **The refusal a screen would never send.**
    ...
    ...    A route guard proves the caller is a manager. It cannot stop manager
    ...    A naming manager B's team, and a run against that team rewrites a
    ...    colleague's whole week. So the request is made by hand, exactly as
    ...    somebody with the URL would make it.
    [Tags]    smoke    scoping    planning    security
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${monday}=    Get Current Date    result_format=%Y-%m-%d
    ${params}=    Create Dictionary
    ...    period_start=${monday}
    ...    period_end=${monday}
    ...    team_id=${SEEDED_TEAM_ID}
    ${response}=    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    403
    ...    msg=A manager rebuilt the week of a team they do not run.

A Manager Cannot Plan The Whole Company
    [Documentation]    **Company-wide is an administrator's act.**
    ...
    ...    Naming no scope at all rewrites the calendar of every assistant the
    ...    company employs, and no manager is answerable for all of them. It is
    ...    refused rather than quietly narrowed to their own teams: being told
    ...    the company had been re-planned when one team was would be worse
    ...    than the refusal.
    [Tags]    smoke    scoping    planning    security
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${monday}=    Get Current Date    result_format=%Y-%m-%d
    ${params}=    Create Dictionary
    ...    period_start=${monday}
    ...    period_end=${monday}
    ${response}=    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    403
    ...    msg=A manager rebuilt the calendar of the whole company.

A Manager Plans Their Own Site
    [Documentation]    The scope above a team, and still only their teams.
    ...
    ...    A site holds several teams and a manager may run only some of them,
    ...    so this is an **intersection** rather than the site's roster —
    ...    otherwise a branch office would be a way to rebuild a colleague's
    ...    week without ever naming their team. The fixture manager runs
    ...    exactly one team here, so exactly one run comes back.
    [Tags]    smoke    scoping    planning
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${monday}=    Get Current Date    result_format=%Y-%m-%d
    ${params}=    Create Dictionary
    ...    period_start=${monday}
    ...    period_end=${monday}
    ...    agency_id=${QA_SITE_ID}
    ${response}=    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=202
    Length Should Be    ${response.json()}    1
    ...    msg=A site-wide computation did not fan out over the caller's teams.
    ${run}=    Set Variable    ${response.json()}[0]
    Should Be Equal    ${run}[team_id]    ${QA_TEAM_ID}
    ...    msg=A site-wide computation reached a team the caller does not run.

A Manager Cannot Poll A Run Of Another Team
    [Documentation]    **Every manager holds real run identifiers.**
    ...
    ...    Starting a run hands the caller one, so the identifier space is not
    ...    a secret. Without a check on the read, a manager could poll a
    ...    colleague's run and learn how much of that team's week would not fit.
    [Tags]    scoping    planning    security
    ${admin}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${admin_headers}=    Authorisation Header    ${admin}
    ${monday}=    Get Current Date    result_format=%Y-%m-%d
    ${params}=    Create Dictionary
    ...    period_start=${monday}
    ...    period_end=${monday}
    ...    team_id=${SEEDED_TEAM_ID}
    ${started}=    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${admin_headers}
    ...    expected_status=202
    ${run_id}=    Set Variable    ${started.json()}[0][id]
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/runs/${run_id}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    403
    ...    msg=A manager polled the planning run of a team they do not run.

A Manager Cannot Open Another Team's Shared Space
    [Documentation]    404, not 403: a private space must look like no space.
    ...
    ...    A 403 would confirm that the team — and the documents in it — exist
    ...    to somebody with no business knowing either.
    [Tags]    scoping    documents    security
    ${token}=    Sign In Through The API    ${SECOND_MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams/${SEEDED_TEAM_ID}/documents
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    404
    ...    msg=Another team's shared space was readable.

An Assistant Cannot Read Another Team's Roster
    [Documentation]    An assistant reads the team they are on, and no other.
    [Tags]    scoping    security
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams/${QA_TEAM_ID}/members
    ...    headers=${headers}
    ...    expected_status=any
    Should Be True    ${response.status_code} >= 400
    ...    msg=An assistant read the roster of a team they are not on.

An Assistant Reads Their Own Team From Their Credential
    [Documentation]    There is nothing to pass, and that is the point.
    ...
    ...    An assistant signing in has no way to know their team's identifier,
    ...    and a screen holding one it read from somewhere else is a screen that
    ...    can be aimed at the wrong roster.
    [Tags]    smoke    scoping
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/team
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Equal    ${response.json()}[id]    ${SEEDED_TEAM_ID}

The Manager's Screens Show The Narrowing
    [Documentation]    The interface and the API agree about the same company.
    ...
    ...    Asserted last, and deliberately after the API half: a screen that
    ...    shows nothing because the request was narrowed and a screen that
    ...    shows nothing because it is broken look identical.
    [Tags]    scoping
    Open The Application
    Sign In As    ${SECOND_MANAGER_EMAIL}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quotes-grid"]    visible
    ${rows}=    Get Element Count    [data-testid="quotes-grid"] .MuiDataGrid-row
    Should Be Equal As Integers    ${rows}    0
    ...    msg=The quote screen showed another team's book.


*** Keywords ***
Form A Second Team
    [Documentation]    Make a site and a team the second manager runs alone.
    ...
    ...    Formed through the API rather than the interface: this suite is about
    ...    what the *server* narrows, and building the fixture by clicking would
    ...    make a failure here look like a failure of the sites screen.
    ${suffix}=    Unique Suffix
    Set Suite Variable    ${QA_SITE}    QA Portee ${suffix}
    Set Suite Variable    ${QA_TEAM}    QA Equipe Portee ${suffix}
    ${site}=    Create An Agency Through The API    ${QA_SITE}
    Set Suite Variable    ${QA_SITE_ID}    ${site}[id]
    ${manager}=    Account Id By Email    ${SECOND_MANAGER_EMAIL}
    ${team}=    Create A Team Through The API    ${QA_TEAM}    ${QA_SITE_ID}    ${manager}
    Set Suite Variable    ${QA_TEAM_ID}    ${team}[id]
    Remember The Seeded Team

Remember The Seeded Team
    [Documentation]    Find the team every seeded person and quote belongs to.
    ...
    ...    Read rather than derived. The seeder's identifier is a hash of the
    ...    team's name, so spelling one here would break silently the day the
    ...    seeded name changes.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams
    ...    headers=${headers}
    ...    expected_status=200
    FOR    ${team}    IN    @{response.json()}
        IF    '${team}[id]' != '${QA_TEAM_ID}'
            Set Suite Variable    ${SEEDED_TEAM_ID}    ${team}[id]
            RETURN
        END
    END
    Fail    msg=The seeded team could not be found.

Remove Every Fixture And Close
    [Documentation]    Leave the stack exactly as the suite found it.
    IF    '${QA_TEAM_ID}' != '${EMPTY}'
        Remove A Team Through The API    ${QA_TEAM_ID}
    END
    IF    '${QA_SITE_ID}' != '${EMPTY}'
        Remove An Agency Through The API    ${QA_SITE_ID}
    END
    Close Browser    ALL

Take A Screenshot On Failure
    [Documentation]    Capture the screen when a test fails.
    ...
    ...    A failure with no picture is a failure somebody has to reproduce
    ...    locally before they can start reading it.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
