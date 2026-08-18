*** Settings ***
Documentation    Skills — the catalogue, and the one thing an assistant declares
...              about themselves that changes who the planner may send them to.
...
...              The catalogue half is the certification catalogue's twin, and
...              is not re-proved here: suite 25 already asserts the locked
...              code, the malformed-code refusal and the delete that is
...              refused while anything refers to the entry. What this suite
...              exists for is the half that has no twin.
...
...              An assistant **adds their own skills**, with no approval step,
...              and the safeguard is that every manager and administrator is
...              notified instead. So three things are worth proving rather
...              than trusting: an assistant really can declare one and it
...              really reaches their record. The supervisors really are told;
...              and a manager really can withdraw it — while there is no
...              route at all by which a manager *declares* one for somebody
...              else.
...
...              The entry and the declaration this suite creates are removed
...              by the last test and again in the teardown, so the suite runs
...              twice with the same result.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Skill Catalogue
Suite Teardown   Remove Every Trace And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# Filled in by the setup: a code no other run produces, so two runs against the
# same stack do not collide on the unique index.
${QA_CODE}          ${EMPTY}
${QA_LABEL}         ${EMPTY}


*** Test Cases ***
The Catalogue Lists What The Agency Recognises
    [Documentation]    The seeded skills are there to be declared and required.
    [Tags]    smoke    skills
    Wait For Elements State    [data-testid="skills-grid"]    visible
    ${rows}=    Get Element Count    [data-testid="skills-grid"] .MuiDataGrid-row
    Should Be True    ${rows} > 0

The Screen Says What A Skill Is For
    [Documentation]    A catalogue nobody understands is a catalogue nobody fills.
    [Tags]    skills
    Wait For Elements State    [data-testid="skills-explained"]    visible

A Malformed Code Is Refused Before It Can Be Stored
    [Documentation]    An accented code is not a code.
    ...
    ...    The same rule as the certification catalogue, and asserted again
    ...    because the two screens are separate components: a regression in one
    ...    says nothing about the other.
    [Tags]    skills    validation
    Click    [data-testid="new-skill"]
    Wait For Elements State    [data-testid="skill-dialog"]    visible
    Fill Text    [data-testid="skill-code"]    LEVÉ
    Fill Text    [data-testid="skill-label"]    Competence accentuee
    Get Attribute    [data-testid="save-skill"]    disabled
    [Teardown]    Click    [data-testid="cancel-skill"]

A Skill Is Added To The Catalogue
    [Documentation]    The catalogue is a manager's, even though declarations are not.
    [Tags]    smoke    skills
    Click    [data-testid="new-skill"]
    Wait For Elements State    [data-testid="skill-dialog"]    visible
    Fill Text    [data-testid="skill-code"]    ${QA_CODE}
    Fill Text    [data-testid="skill-label"]    ${QA_LABEL}
    Click    [data-testid="save-skill"]
    Sleep    2s

    ${stored}=    The QA Skill Type
    Should Not Be Equal    ${stored}    ${None}    msg=The skill was not stored.
    Should Be Equal    ${stored}[label]    ${QA_LABEL}

The Code Cannot Be Changed Once The Entry Exists
    [Documentation]    Renaming it would un-skill everybody who declared it.
    [Tags]    smoke    skills
    Open The QA Skill Type
    Get Attribute    [data-testid="skill-code"]    disabled
    [Teardown]    Click    [data-testid="cancel-skill"]

An Assistant Declares The Skill On Their Own Account
    [Documentation]    **The one thing on that page its owner may write.**
    ...
    ...    A certification is a claim about what somebody was awarded, so a
    ...    manager records it. A skill is a claim about what they can do, and
    ...    an assistant who cannot say they speak Portuguese is one the agency
    ...    does not know it has. This is the whole feature, clicked rather than
    ...    called.
    [Tags]    smoke    skills
    Sign In As An Assistant
    Navigate To    /me
    Wait For Elements State    [data-testid="my-skills"]    visible
    Select Options By    [data-testid="my-new-skill"]    value    ${QA_CODE}
    Click    [data-testid="declare-my-skill"]
    Sleep    2s

    Wait For Elements State    [data-testid="my-skill-${QA_CODE}"]    visible
    ${declared}=    The Assistant's QA Skill
    Should Not Be Equal    ${declared}    ${None}
    ...    msg=The declaration never reached the assistant's record.

The Screen Says The Declaration Takes Effect At Once
    [Documentation]    A control that silently widens what you may be sent to.
    ...
    ...    There is no approval step, so the honest answer to "will somebody
    ...    check this?" is *yes, afterwards*. The alert is where that is said,
    ...    and it is on screen rather than in a comment for a reason.
    [Tags]    skills
    Wait For Elements State    [data-testid="my-skills-explained"]    visible

The Picker No Longer Offers What Is Already Declared
    [Documentation]    A duplicate would be stored twice and read once.
    [Tags]    skills
    ${options}=    Get Element Count
    ...    [data-testid="my-new-skill"] option[value="${QA_CODE}"]
    Should Be Equal As Integers    ${options}    0

The Supervisors Are Told
    [Documentation]    **This is what makes an unapproved declaration safe.**
    ...
    ...    Somebody adding a skill widens what the planner may send them to.
    ...    The notification is what leaves a manager able to challenge it
    ...    before the next run acts on it, and it is asserted through the API
    ...    rather than the badge because it is written by the worker — the
    ...    badge is one push away from a race this suite has no business
    ...    timing.
    [Tags]    smoke    skills    notifications
    Wait Until Keyword Succeeds    20x    2s    The Manager Was Notified

The Notification Names The Code As Well As The Label
    [Documentation]    The code is what a requirement is matched on.
    ...
    ...    A supervisor deciding whether somebody has over-claimed needs to
    ...    know which requirement the declaration just satisfied, and the
    ...    free-text name does not say.
    [Tags]    skills    notifications
    ${notification}=    The Skill Notification
    Should Contain    ${notification}[body]    ${QA_CODE}

A Manager Withdraws The Declaration
    [Documentation]    The correction an unapproved declaration depends on.
    ...
    ...    Its owner may take back what they said; so may a manager or an
    ...    administrator who believes it is wrong. Both go through the same
    ...    service check.
    [Tags]    smoke    skills
    ${hca}=    Target Assistant
    ${declared}=    The Assistant's QA Skill
    ${headers}=    Manager Headers
    DELETE
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/skills/${declared}[id]
    ...    headers=${headers}
    ...    expected_status=204

    ${left}=    The Assistant's QA Skill
    Should Be Equal    ${left}    ${None}    msg=The declaration survived its withdrawal.

There Is No Route By Which A Manager Declares One
    [Documentation]    A supervisor may withdraw a claim, not make one.
    ...
    ...    A skill is a claim about what somebody can do. Nothing lets a
    ...    manager put one in another person's mouth, and that is a routing
    ...    decision rather than an oversight — so the path answers 405, not
    ...    403: the method does not exist at all.
    [Tags]    skills    security
    ${hca}=    Target Assistant
    ${headers}=    Manager Headers
    ${body}=    Create Dictionary    name=${QA_LABEL}    code=${QA_CODE}
    POST
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/skills
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=405

An Unreferenced Skill Is Deleted From The Catalogue
    [Documentation]    The suite's own clean-up, written as the test it is.
    ...
    ...    Deleting what this run created is what makes the suite runnable
    ...    twice. It runs after the withdrawal above, which is what makes it
    ...    succeed: an entry somebody has declared is refused.
    [Tags]    smoke    skills
    Sign In As    ${MANAGER_EMAIL}
    Open The QA Skill Type
    Click    [data-testid="delete-skill"]
    Sleep    2s

    ${stored}=    The QA Skill Type
    Should Be Equal    ${stored}    ${None}    msg=The skill survived its own deletion.


*** Keywords ***
Open The Skill Catalogue
    ${suffix}=    Unique Suffix
    ${digits}=    Replace String    ${suffix}    -    ${EMPTY}
    Set Suite Variable    ${QA_CODE}    QAS${digits}
    Set Suite Variable    ${QA_LABEL}    Competence QA ${suffix}
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /skills
    Wait For Elements State    [data-testid="skills-grid"]    visible

Remove Every Trace And Close
    [Documentation]    Strip this run's declaration and entry however it ended.
    ...
    ...    In that order, because the catalogue refuses to delete an entry
    ...    anybody has declared — which is the behaviour the suite sets up on
    ...    purpose. Reported rather than ignored: a cleanup that fails quietly
    ...    breaks tomorrow's run instead of today's.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Strip Every Trace Of The QA Skill
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    The QA skill was left behind: ${error}
    END

Manager Headers
    [Documentation]    Return the bearer header for the seeded manager.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

Sign In As An Assistant
    [Documentation]    Sign the browser in as the assistant this suite borrows.
    Sign In As    ${ASSISTANT_EMAIL}

The QA Skill Type
    [Documentation]    Return this run's catalogue entry, or ``None``.
    ...
    ...    Retired entries are included, so a lookup does not report an entry
    ...    that is merely out of use as deleted.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500    include_inactive=true
    ${response}=    GET
    ...    ${API_URL}/api/v1/skills
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [e for e in $response.json() if e["code"]=="${QA_CODE}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Open The QA Skill Type
    [Documentation]    Find this run's entry on the grid and open its dialog.
    Navigate To    /skills
    Wait For Elements State    [data-testid="skills-grid"]    visible
    Click    [data-testid="edit-skill-${QA_CODE}"]
    Wait For Elements State    [data-testid="skill-dialog"]    visible

Target Assistant
    [Documentation]    Return the assistant whose account this suite signs in as.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    search=Martin
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${found}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${found}    msg=No seeded assistant named Martin.
    RETURN    ${found}[0]

The Assistant's QA Skill
    [Documentation]    Return this run's declaration on the assistant, or ``None``.
    ${hca}=    Target Assistant
    ${matching}=    Evaluate
    ...    [s for s in $hca["skills"] if s["code"]=="${QA_CODE}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

The Skill Notification
    [Documentation]    Return the manager's newest ``skill-added`` notification.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/notifications
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [n for n in $response.json() if n["kind"]=="skill-added" and "${QA_CODE}" in (n["body"] or "")]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

The Manager Was Notified
    [Documentation]    Fail until the worker has written the notification.
    ${notification}=    The Skill Notification
    Should Not Be Equal    ${notification}    ${None}
    ...    msg=No supervisor was told about the declaration.

Strip Every Trace Of The QA Skill
    [Documentation]    Withdraw the declaration, then delete the entry.
    ${headers}=    Manager Headers
    ${declared}=    The Assistant's QA Skill
    IF    ${declared} is not None
        ${hca}=    Target Assistant
        DELETE
        ...    ${API_URL}/api/v1/hcas/${hca}[id]/skills/${declared}[id]
        ...    headers=${headers}
        ...    expected_status=204
    END
    ${entry}=    The QA Skill Type
    IF    ${entry} is not None
        DELETE
        ...    ${API_URL}/api/v1/skills/${entry}[id]
        ...    headers=${headers}
        ...    expected_status=204
    END

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
