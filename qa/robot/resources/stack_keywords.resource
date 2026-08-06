*** Settings ***
Documentation    Getting the application up before the campaign drives it.
...
...              The campaign runs against the real stack, so the stack has to
...              exist. Left to itself the first keyword to notice is
...              ``New Page``, and what it reports is a browser error — "Could
...              not find active page" — which says nothing about the fact that
...              nothing is listening on port 5173. The cost of that is a
...              developer reading Playwright's traces for a while before
...              working out that the answer is ``docker compose up``.
...
...              So the campaign brings the stack up itself, and when it cannot,
...              says so in those words.

Library          Process
Library          RequestsLibrary
Resource         config.resource


*** Keywords ***
Ensure The Stack Is Up
    [Documentation]    Bring the stack up if it is not already serving.
    ...
    ...    Checked before it is started, and the check is the same one either
    ...    way. A developer with the stack already running — which is the usual
    ...    case — pays one HTTP request for this and nothing else; ``compose
    ...    up`` is only reached when the check actually fails.
    ${serving}=    Run Keyword And Return Status    The Stack Is Serving
    IF    ${serving}
        Log    The stack is already up.    console=${True}
        RETURN
    END
    IF    not ${START_STACK}
        Fail
        ...    The stack is not running and START_STACK is False. Start it with
        ...    `docker compose ${COMPOSE_FILES} up -d --build`, or drop the
        ...    variable to let the campaign start it.
    END
    Start The Stack
    Wait Until The Stack Is Serving

Start The Stack
    [Documentation]    Run ``docker compose up`` and wait for it to return.
    ...
    ...    Detached, so this returns once the containers have been created
    ...    rather than blocking on their logs. Readiness is a separate question
    ...    and a separate keyword: compose considers a container started long
    ...    before uvicorn has finished importing the application.
    Log    Starting the stack; the first run builds the images.    console=${True}
    ${result}=    Run Process
    ...    docker    compose    @{COMPOSE_FILES.split()}    up    -d    --build
    ...    cwd=${COMPOSE_ROOT}
    ...    stdout=${OUTPUT DIR}/compose-up.log
    ...    stderr=STDOUT
    ...    timeout=${STACK_TIMEOUT}
    IF    ${result.rc} != 0
        Fail
        ...    `docker compose up` exited ${result.rc}. Its output is in
        ...    compose-up.log next to this report.
    END

Wait Until The Stack Is Serving
    [Documentation]    Poll until the application answers, or give up saying so.
    Wait Until Keyword Succeeds
    ...    ${STACK_TIMEOUT}
    ...    ${STACK_POLL}
    ...    The Stack Is Serving
    Log    The stack is serving.    console=${True}

The Stack Is Serving
    [Documentation]    Pass only when the whole stack is ready to be tested.
    ...
    ...    Three things, because any one of them alone is a stack that looks up
    ...    and fails the first test:
    ...
    ...    - the **front-end** answers, or the browser has nothing to load;
    ...    - the **API** answers, or every fixture fails to be created;
    ...    - the **seeded administrator can sign in**, which is the only one of
    ...      the three that proves the migrations ran and the seeder finished.
    ...      An API that is up against an empty database passes the first two
    ...      and fails every suite.
    ${front_end}=    GET    ${BASE_URL}    expected_status=any    timeout=5
    Should Be True    ${front_end.status_code} < 500    The front-end is not serving yet.
    ${api}=    GET    ${API_URL}/docs    expected_status=any    timeout=5
    Should Be True    ${api.status_code} < 500    The API is not serving yet.
    ${credentials}=    Create Dictionary
    ...    email=${ADMIN_EMAIL}
    ...    password=${SEED_PASSWORD}
    ${login}=    POST
    ...    ${API_URL}/api/v1/auth/login
    ...    json=${credentials}
    ...    expected_status=any
    ...    timeout=5
    Should Be Equal As Integers    ${login.status_code}    200
    ...    The database is not seeded yet: the seeded administrator cannot sign in.
