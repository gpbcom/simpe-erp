*** Settings ***
Documentation    Real V8 coverage, collected while the campaign drives the app.
...
...              The point of this file is that "the campaign covers the
...              front-end" stops being a claim and becomes a number somebody
...              can read. Playwright collects JavaScript and CSS coverage from
...              Chromium; Vite emits source maps (``build.sourcemap: true``),
...              so the raw V8 ranges map back to the ``.tsx`` files a reviewer
...              recognises rather than to a minified bundle.
...
...              Every suite that opens a browser starts coverage after the page
...              is loaded and stops it before the browser closes. The per-suite
...              reports are merged into one at the end of the run — a single
...              suite covers a fraction of the app by design, and only the
...              merge answers the question that was asked.

Library          Browser
Library          String
Resource         config.resource


*** Keywords ***
Begin Coverage For
    [Documentation]    Start recording coverage for one suite.
    ...
    ...    ``raw`` rather than a rendered report per suite: rendering twelve
    ...    separate reports and reading them one at a time would tell nobody
    ...    what the campaign covers *together*, which is the only figure that
    ...    matters. ``Merge Coverage Reports`` does the rendering, once, over
    ...    every suite's raw output.
    ...
    ...    ``resetOnNavigation=False`` because this application is a SPA that
    ...    also does full navigations — the theme toggle reloads deliberately,
    ...    and the routing suite types addresses. Resetting on each would
    ...    discard everything recorded before it and report a figure far below
    ...    what the campaign actually exercised.
    [Arguments]    ${suite_name}
    ${slug}=    Replace String Using Regexp    ${suite_name}    [^A-Za-z0-9]+    -
    Run Keyword And Ignore Error
    ...    Start Coverage
    ...    config_file=${COVERAGE_CONFIG}
    ...    coverage_type=all
    ...    path=${COVERAGE_RAW_DIR}/${slug}
    ...    raw=${True}
    ...    resetOnNavigation=${False}

End Coverage
    [Documentation]    Stop recording, leaving the raw data for the merge.
    ...
    ...    Wrapped in ``Run Keyword And Ignore Error`` on purpose. A coverage
    ...    collector that fails must not turn a passing functional suite red:
    ...    the tests are the deliverable and the measurement is the report on
    ...    them, so the measurement failing is a reporting problem, not a
    ...    product one. A run with no coverage output is visible in CI because
    ...    the merge step produces nothing.
    Run Keyword And Ignore Error    Stop Coverage
