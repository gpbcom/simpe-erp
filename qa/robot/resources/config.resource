*** Settings ***
Documentation    Where the stack is, and who the campaign signs in as.
...
...              Everything here is a variable so a run can be pointed at
...              another environment with ``--variable``, rather than the
...              addresses being spelled out in twenty places.


*** Variables ***
${BASE_URL}             http://localhost:5173
${API_URL}              http://localhost:8000
${MAILPIT_URL}          http://localhost:8025

# The seeded credentials. Printed by the seeder on every run; see
# backend/seed/src/seed/dataset.py.
${SEED_PASSWORD}        simple-erp-demo-2026
# The seeded agency's trading name. Used to exercise the name clash when
# founding an agency, because it is always there and never edited.
${SEEDED_COMPANY_NAME}  Aide et Presence Paris
${ADMIN_EMAIL}          admin@simple-erp.fr
${MANAGER_EMAIL}        manager@simple-erp.fr
${ASSISTANT_EMAIL}      luc.martin@simple-erp.fr
${OTHER_ASSISTANT}      amina.benali@simple-erp.fr

# Headless by default. A developer watching a failure runs with
# ``--variable HEADLESS:False`` and sees the browser.
${HEADLESS}             ${True}
${BROWSER_TIMEOUT}      15s
# Long enough for the broker round trip — an assistant submits, the API
# publishes, the worker consumes and writes the row, the API pushes the SSE
# frame — without being so long that a genuinely broken pipeline takes a
# minute to report.
${EVENT_TIMEOUT}        20s

# The campaign brings the stack up itself when it is not already running, so a
# run started from an editor's test view does not fail with a browser error
# that says nothing about the real cause. Set to False to run against a stack
# somebody else is managing — a staging environment, or a CI job that started
# the services as a separate step.
${START_STACK}          ${True}
${COMPOSE_ROOT}         ${CURDIR}/../../..
${COMPOSE_FILES}        -f docker-compose.yaml -f docker-compose.dev.yaml
# Generous, because the first run of the day builds the images and migrates an
# empty database. A stack that is already up satisfies the readiness check on
# the first attempt and none of this is waited on.
${STACK_TIMEOUT}        6 minutes
${STACK_POLL}           3s

# Where the coverage collector reads its thresholds from. Kept out of this file
# because monocart wants JSON, and a threshold is a policy decision that should
# be visible on its own rather than buried among addresses.
${COVERAGE_CONFIG}      ${CURDIR}/../../coverage.config.json
# Each suite writes its raw V8 output into its own directory here; the merge
# step at the end of the run turns the lot into one report.
${COVERAGE_RAW_DIR}     ${OUTPUT DIR}/coverage-raw
