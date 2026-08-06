*** Settings ***
Documentation    The GUI campaign.
...
...              Drives the real application in a real browser, against the
...              real API. This file exists to make that first word true: it
...              runs once, before any suite, and leaves a stack behind that
...              the suites can assume.
...
...              It is a directory initialisation file rather than a setup on
...              each suite because starting the stack fourteen times would be
...              fourteen times the wait, and because a suite that checked for
...              itself would still have to decide what to do about the other
...              thirteen.
...
...              Running one suite by its own path — ``robot
...              qa/robot/suites/01_auth.robot`` — bypasses this, since the
...              file is then the root suite and its directory is never
...              entered. Run the directory and select with ``--suite`` instead;
...              that is what the editor's test view does.

Resource         ../resources/stack_keywords.resource

Suite Setup      Ensure The Stack Is Up
