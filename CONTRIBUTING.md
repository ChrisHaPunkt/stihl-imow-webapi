Contributing

Thanks for your interest. Short guidelines:

- Use feature branches named `feature/<short-description>` and open PRs against `main`.
- Tests must not include real credentials. For integration tests, copy `tests/secrets.py.example` to `tests/secrets.py` locally and never commit it.
- Run tests locally with `pytest -q` and ensure linting passes.
- PRs should include a short description, test plan, and link to relevant issues.

Testing and CI
- This repo includes a GitHub Actions workflow that runs hassfest and pytest on pull requests. See .github/workflows/ci.yml for details.