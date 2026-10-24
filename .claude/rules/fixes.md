# Bug fixes and changes to behavior

The integration has many users. Each user gets different data from the Wiener Netze API.
A fix that works with the data of one user can break the integration for other users.

## Before you make a plan
- Read the code that the change touches yourself. Do not trust the description of the user about how the code works.
- Find all callers and all code paths that use the changed code.
- Find the root cause. Do not fix only the symptom with the data of one user.
- Identify which data variants go through the changed code, for example:
  - Zählpunkt types (`AnlagenType`: TAGSTROM, NACHTSTROM, WAERMEPUMPE, STROM, WANDLER, BEZUG)
  - Consumption and feeding (`RoleType`: V001, V002, E001, E002)
  - Granularity: quarter-hour, hour, day, meter reading (`ValueType`, `Resolution`)
  - Units (`WH`, `KWH`)
  - Missing, partial, empty or `null` values, and gaps in time series
  - B2C and B2B API, and accounts with more than one Zählpunkt
  - Time zones and the change to and from daylight saving time
- Ask the user for an anonymized example of their API response if the problem depends on their data.

## Before you change code
- Tell the user in short bullets:
  - the root cause
  - the code that the fix changes
  - the other functions and data variants that the change can affect
- Ask the user to confirm that they understand the current code and the effect of the fix.
- Ask the user to confirm that the fix must not change behavior for other users.
- Wait for the confirmation. Do not start to write code before.

## After you make a plan or a fix
- Do a separate review of the plan or the diff. Look only for problems that the change causes:
  - other data variants from the list above that the change breaks
  - changed behavior of existing sensors, statistics or config entries for current users
  - removed fallbacks and changed default values
- Tell the user each problem that you find. Fix it or ask the user how to continue.

## Regression tests
- Write a test that fails without the fix and passes with the fix.
- Add tests for the other data variants that go through the changed code. Make sure that they still pass.
- Do not change existing tests so that they pass with the fix. If an existing test fails, stop and tell the user. A failed test can show a regression for other users.
