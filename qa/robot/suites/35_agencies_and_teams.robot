*** Settings ***
Documentation    Agencies and teams — the two organisational levels the company
...              gained, and the rules that make each of them mean something.
...
...              A company used to be one place with one workforce. It is now a
...              company with **sites**, and each site has **teams** — and the
...              team is the unit the planner works in: a run rebuilds one
...              team's week and nobody else's.
...
...              Four rules are worth proving rather than trusting, because each
...              is a question about *other rows* that no form can answer about
...              itself, and each fails silently if it stops holding:
...
...              - the first site of a company is its head office, and a second
...                one is refused;
...              - a site cannot be closed while anybody or any team is still
...                attached to it, which is the only thing standing between a
...                delete and a team based nowhere;
...              - a person is on exactly one team, so adding them to a second
...                is refused rather than silently moving them — two teams would
...                each plan them and each delete the other's week;
...              - everybody on a team may add a document to its shared space,
...                which is unusual on this surface and is the point.
...
...              Every fixture this suite makes is removed by the teardown, by
...              identifier, so the suite runs twice with the same result.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Sites Screen
Suite Teardown   Remove Every Fixture And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# Filled in by the setup: names no other run produces, so two runs against the
# same stack do not collide on the unique index over (company, name).
${QA_SITE}          ${EMPTY}
${QA_TEAM}          ${EMPTY}
${QA_SITE_ID}       ${EMPTY}
${QA_TEAM_ID}       ${EMPTY}


*** Test Cases ***
The Sites Screen Lists Where The Company Operates From
    [Documentation]    The seeded head office and its branch are both there.
    [Tags]    smoke    agencies
    Wait For Elements State    [data-testid="agencies-grid"]    visible
    ${rows}=    Get Element Count    [data-testid="agencies-grid"] .MuiDataGrid-row
    Should Be True    ${rows} > 1
    ...    msg=A company that is only its head office demonstrates nothing.

The Screen Says What A Site Is For
    [Documentation]    A level nobody understands is a level nobody fills.
    [Tags]    agencies
    Wait For Elements State    [data-testid="agencies-explained"]    visible

A New Site Is A Branch, Whatever Was Asked For
    [Documentation]    **The rule the whole level rests on.**
    ...
    ...    The first site of a company is its head office and every later one is
    ...    a branch. Both are questions about *other rows*, so the payload's
    ...    type is overwritten rather than trusted — and this asserts the
    ...    overwrite, because a form that silently changes a value reads as a
    ...    bug and a form that does not would let the second administrator
    ...    through the door declare their own office the head one.
    [Tags]    smoke    agencies
    ${site}=    Create An Agency Through The API    ${QA_SITE}    hq
    Set Suite Variable    ${QA_SITE_ID}    ${site}[id]
    Should Be Equal    ${site}[agency_type]    office
    ...    msg=A second head office was accepted.
    Should Not Be True    ${site}[is_headquarters]

A Branch Carries None Of The Company's Legal Identity
    [Documentation]    A site *is* a company, so this is not free.
    ...
    ...    The record behind a site carries the SIRET, the VAT number and the
    ...    account invoices are paid into, because the head office is where the
    ...    business is registered. The projection these routes return declares
    ...    none of it — and it must not, because reading a site is open to every
    ...    signed-in account, including an assistant.
    [Tags]    smoke    agencies    security
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/agencies/${QA_SITE_ID}
    ...    headers=${headers}
    ...    expected_status=200
    ${site}=    Set Variable    ${response.json()}
    Dictionary Should Not Contain Key    ${site}    iban
    ...    msg=The sites route published the company's bank account.
    Dictionary Should Not Contain Key    ${site}    registration_number
    Dictionary Should Not Contain Key    ${site}    bic

A Site Nobody Works At Can Be Closed
    [Documentation]    And one that holds people or teams cannot.
    ...
    ...    Asserted in that order deliberately: the refusal is what protects a
    ...    team from being based at a site that no longer exists, and the counts
    ...    in the message are the actionable part.
    [Tags]    agencies
    ${spare}=    Create An Agency Through The API    ${QA_SITE}-spare
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/agencies/${spare}[id]
    ...    headers=${headers}
    ...    expected_status=204
    Should Be Equal    ${response.text}    ${EMPTY}

The Head Office Cannot Be Closed While The Company Has Branches
    [Documentation]    Closing it would leave every quote printing without a SIRET.
    [Tags]    agencies
    ${head}=    The Seeded Head Office
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/agencies/${head}[id]
    ...    headers=${headers}
    ...    expected_status=any
    Should Be True    ${response.status_code} >= 400
    ...    msg=The head office was closed while the company still had branches.

A Team Is Formed At A Site, Under One Manager
    [Documentation]    And the manager is on it from the moment it exists.
    ...
    ...    "Exactly one manager" is a cardinality no flag on a roster can hold,
    ...    so it is a field on the team. The creating call enrols them as a
    ...    member too, so a roster never has to explain why the person in charge
    ...    is missing from it.
    [Tags]    smoke    teams
    ${manager}=    Account Id By Email    ${MANAGER_EMAIL}
    ${team}=    Create A Team Through The API    ${QA_TEAM}    ${QA_SITE_ID}    ${manager}
    Set Suite Variable    ${QA_TEAM_ID}    ${team}[id]
    Should Be Equal    ${team}[manager_user_id]    ${manager}
    Should Be Equal As Integers    ${team}[member_count]    1
    ...    msg=The team's own manager is not on it.

A Team Named Twice Is Refused
    [Documentation]    Two teams of one name are two rows nobody can tell apart.
    [Tags]    teams
    ${manager}=    Account Id By Email    ${MANAGER_EMAIL}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    name=${QA_TEAM}
    ...    agency_id=${QA_SITE_ID}
    ...    manager_user_id=${manager}
    ${response}=    POST
    ...    ${API_URL}/api/v1/teams
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    409

Attaching Somebody To A Site Moves Them Off The Old One
    [Documentation]    **One act, one form.**
    ...
    ...    Everybody belongs to exactly one site, so the old membership has to
    ...    go either way — the only question was whether an operator had to
    ...    remove it by hand first. It does not: the transfer is one call, and
    ...    the state in between, somebody attached to no site at all, is one
    ...    nothing else in the system expects.
    ...
    ...    The account is put back at the end, because the seeded organisation
    ...    is read-only to this campaign.
    [Tags]    smoke    agencies
    ${account}=    Account Id By Email    ${SECOND_MANAGER_EMAIL}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    member_kind=user    member_id=${account}
    ${response}=    POST
    ...    ${API_URL}/api/v1/agencies/${QA_SITE_ID}/members
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    201
    ...    msg=A transfer between sites was refused instead of performed.

    ${moved}=    GET
    ...    ${API_URL}/api/v1/agencies/${QA_SITE_ID}/members
    ...    headers=${headers}
    ...    expected_status=200
    ${ids}=    Evaluate    [m["member_id"] for m in $moved.json()]
    Should Contain    ${ids}    ${account}

    ${head}=    The Seeded Head Office
    ${previous}=    GET
    ...    ${API_URL}/api/v1/agencies/${head}[id]/members
    ...    headers=${headers}
    ...    expected_status=200
    ${old_ids}=    Evaluate    [m["member_id"] for m in $previous.json()]
    Should Not Contain    ${old_ids}    ${account}
    ...    msg=The old membership survived the transfer; they are on two sites.

    Put The Account Back At The Head Office    ${account}

A Team Refuses Somebody Based At Another Site
    [Documentation]    **A team is people at a place.**
    ...
    ...    The planner measures every round from the team's site, so somebody
    ...    based elsewhere would be routed from a depot they never travel to.
    ...
    ...    This one stays a refusal rather than becoming a move, and the
    ...    distinction is worth stating: a site transfer is one act the operator
    ...    plainly means, while silently *relocating* somebody so they can join
    ...    a team is a second decision they did not ask for. The seeded
    ...    assistants all work at the head office, so this team cannot have one.
    [Tags]    smoke    teams    planning
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${listing}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    headers=${headers}
    ...    expected_status=200
    ${assistant}=    Set Variable    ${listing.json()}[0]
    ${body}=    Create Dictionary    member_kind=hca    member_id=${assistant}[id]
    ${response}=    POST
    ...    ${API_URL}/api/v1/teams/${QA_TEAM_ID}/members
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    422
    ...    msg=A team took somebody who works at another site.

A Team That Holds No Quote Can Be Disbanded
    [Documentation]    And one that holds work cannot, because nothing would plan it.
    ...
    ...    ``quotes.team_id`` carries no foreign key, so nothing at the database
    ...    level stops a quote outliving its team — and a quote naming a team
    ...    that no longer exists is one no planning run will ever read again.
    [Tags]    teams
    ${manager}=    Account Id By Email    ${MANAGER_EMAIL}
    ${spare_site}=    Create An Agency Through The API    ${QA_SITE}-tmp
    ${admin}=    Account Id By Email    ${ADMIN_EMAIL}
    ${spare}=    Create A Team Through The API    ${QA_TEAM}-tmp    ${spare_site}[id]    ${admin}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/teams/${spare}[id]
    ...    headers=${headers}
    ...    expected_status=204
    Remove An Agency Through The API    ${spare_site}[id]

The Teamspace Accepts A Document And Gives It Back
    [Documentation]    **Everybody on the team may add one, and that is the point.**
    ...
    ...    A shared space only one person can fill is a shared space nobody
    ...    uses. What is narrower is *removing*: whoever added it, the team's
    ...    manager, or an administrator — because anybody may add one, and
    ...    anybody being able to remove one would make the space a place where
    ...    work disappears without a name attached.
    [Tags]    smoke    teams    documents
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${pdf}=    Evaluate    b"%PDF-1.4\\n1 0 obj\\n<<>>\\nendobj\\n"
    ${files}=    Create Dictionary    document=${{ ("qa.pdf", $pdf, "application/pdf") }}
    ${uploaded}=    POST
    ...    ${API_URL}/api/v1/teams/${QA_TEAM_ID}/documents
    ...    files=${files}
    ...    headers=${headers}
    ...    expected_status=201
    ${document}=    Set Variable    ${uploaded.json()}
    Should Be Equal    ${document}[content_type]    application/pdf
    ...    msg=The store trusted the declared type rather than the file's bytes.

    ${downloaded}=    GET
    ...    ${API_URL}/api/v1/teams/${QA_TEAM_ID}/documents/${document}[id]
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Equal As Integers    ${downloaded.content.__len__()}    ${document}[size_bytes]

    DELETE
    ...    ${API_URL}/api/v1/teams/${QA_TEAM_ID}/documents/${document}[id]
    ...    headers=${headers}
    ...    expected_status=204

The Teamspace Publishes What It Accepts
    [Documentation]    So a client refuses a file before uploading it, not after.
    [Tags]    teams    documents
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/teams/document-constraints
    ...    headers=${headers}
    ...    expected_status=200
    ${limits}=    Set Variable    ${response.json()}
    Should Be True    ${limits}[max_upload_bytes] > 0
    Should Not Be Empty    ${limits}[accepted_content_types]

The Teams Screen Shows What Was Made
    [Documentation]    The API and the screen agree about the same company.
    [Tags]    teams
    Navigate To    /teams
    Wait For Elements State    [data-testid="teams-grid"]    visible
    Wait For Elements State    [data-testid="team-people-${QA_TEAM_ID}"]    visible
    Wait For Elements State    [data-testid="team-documents-${QA_TEAM_ID}"]    visible


*** Keywords ***
Open The Sites Screen
    [Documentation]    Sign in as an administrator and open the sites grid.
    ${suffix}=    Unique Suffix
    Set Suite Variable    ${QA_SITE}    QA Antenne ${suffix}
    Set Suite Variable    ${QA_TEAM}    QA Equipe ${suffix}
    Open The Application
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /agencies

Put The Account Back At The Head Office
    [Documentation]    Undo a transfer this suite made, site and team.
    ...
    ...    Two calls, because moving somebody between sites also takes them off
    ...    a team based at the old one — that is the documented consequence, and
    ...    restoring the site alone would leave the seeded team one member short
    ...    for every later run.
    [Arguments]    ${account}
    ${head}=    The Seeded Head Office
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${site_body}=    Create Dictionary    member_kind=user    member_id=${account}
    POST
    ...    ${API_URL}/api/v1/agencies/${head}[id]/members
    ...    json=${site_body}
    ...    headers=${headers}
    ...    expected_status=any
    ${teams}=    GET
    ...    ${API_URL}/api/v1/teams
    ...    headers=${headers}
    ...    expected_status=200
    FOR    ${team}    IN    @{teams.json()}
        IF    '${team}[id]' != '${QA_TEAM_ID}'
            POST
            ...    ${API_URL}/api/v1/teams/${team}[id]/members
            ...    json=${site_body}
            ...    headers=${headers}
            ...    expected_status=any
            RETURN
        END
    END

Remove Every Fixture And Close
    [Documentation]    Leave the stack exactly as the suite found it.
    ...
    ...    The team goes before the site, because a site holding a team refuses
    ...    to close — the same refusal this suite asserts.
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
