*** Settings ***
Documentation    Merge every suite's raw coverage into one report.
...
...              Numbered 99 so Robot runs it last: it has nothing to exercise,
...              it reads what the fourteen suites before it recorded. A single
...              suite covers a fraction of the application by design — the
...              calendar suite never opens the map — so only the merge answers
...              the question "what does the campaign cover".
...
...              **This suite never fails the run.** A coverage collector that
...              could not read its input is a reporting problem. The functional
...              suites are the deliverable, and turning them red because a
...              report did not render would be reporting the wrong failure.
...              A missing report is visible in CI as a missing artefact.

Library          Browser
Library          OperatingSystem
Resource         ../resources/config.resource


*** Test Cases ***
Merge The Coverage Recorded By Every Suite
    [Documentation]    Produce one report over the whole campaign.
    [Tags]    coverage
    ${exists}=    Run Keyword And Return Status
    ...    Directory Should Exist    ${COVERAGE_RAW_DIR}
    Skip If    not ${exists}
    ...    No raw coverage was recorded. The browsers may not be installed.

    ${status}    ${result}=    Run Keyword And Ignore Error
    ...    Merge Coverage Reports
    ...    ${COVERAGE_RAW_DIR}
    ...    ${OUTPUT DIR}/coverage
    ...    config_file=${COVERAGE_CONFIG}
    ...    name=simple-erp front-end — GUI campaign

    Run Keyword If    '${status}' == 'FAIL'
    ...    Log    Coverage could not be merged: ${result}    level=WARN
    Run Keyword If    '${status}' == 'PASS'
    ...    Log    Coverage report written to ${result}    level=INFO
