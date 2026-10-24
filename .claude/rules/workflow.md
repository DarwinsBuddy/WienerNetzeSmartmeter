## Setup
- Create a virtual environment in `.venv` and install the test dependencies: `pip install -r tests/requirements.txt`.

## Checks
- Run `coverage run -m pytest && coverage report -m` before you complete a task. Make sure that all tests pass.
- Add tests for the code that you change. Do not decrease the total coverage.
- Run the flake8 checks of the CI job "Tests" before you complete a task. Make sure that the first command has no findings:
  - `flake8 custom_components/wnsm --count --select=E9,F63,F7,F82 --show-source --statistics --config tests/setup.cfg`
  - `flake8 custom_components/wnsm --count --exit-zero --max-complexity=10 --statistics --config tests/setup.cfg`

## Scope
- Do only the task at hand.
- Ask when the request is ambiguous.
- Choose the simpler option when in doubt.

## Git
- Never run `git commit`, `git push`, or create a branch on your own. Do these only when asked explicitly.
- Leave finished work as uncommitted changes and report the changed files.
- Never skip the git hooks (`git commit --no-verify`). Fix the finding instead.
