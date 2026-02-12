
# Contributing to Cogitus <!-- omit in toc -->

Thank you for your interest in contributing to Cogitus! We welcome
all contributions, big or small.

If you are not sure where to start, please take a look at the [open
issues](https://github.com/seapagan/cogitus/issues). If you have an
idea for a new feature or would like to report a bug, please open a new issue.

We also welcome contributions to the documentation. If you find any errors or
would like to suggest improvements, please open a new issue or submit a pull

## Prerequisites

- This project requires **Python 3.10** or higher.

- We use [uv](https://docs.astral.sh/uv/) to manage our dependencies. You should
have this installed as well. You can install `uv` by following the instructions
on their [website](https://docs.astral.sh/uv/getting-started/installation/).

`uv` can be used to actually install Python, even if you do not have it
installed locally (either by system, pyenv or similar).

For example, to install Python 3.14 using `uv`, you can run the following command:

```console
uv python install 3.14
```

If you already have a Python version installed, uv will use this.

## Getting Started

Before you start contributing, please make sure you have read and understood our
[Code of
Conduct](https://github.com/seapagan/cogitus/blob/main/CODE_OF_CONDUCT.md) and
[License](https://github.com/seapagan/cogitus/blob/main/LICENSE.txt).

To get started, follow these steps:

1. Fork the repository and clone it to your local machine.
2. Install the required dependencies (see [next section](#install-dependencies)).
3. Create a new branch for your changes: `git checkout -b my-new-feature`.
4. Make your changes and commit them: `git commit -am 'Add some feature'`.
5. Push your changes to your fork: `git push origin my-new-feature`.
6. Create a new pull request.

## Install Dependencies

Run the following command to create a local virtualenv and install the required
dependencies. We need the optional extras installed so the tests pass:

```console
uv sync --all-extras
```

The `.venv` folder is already in the `.gitignore` file so will not be committed
to the repository. This is where the virtual environment will be created.

You then need to activate the virtual environment:

```console
source .venv/bin/activate
```

From here you can start working on the project. If you are using an IDE such as
VSCode or PyCharm, you can set their Python interpreter setting to use
the virtual environment that has just been created.

## Install Git Pre-Commit hooks

Please do this if you are intending to submit a PR. It will check commits
locally before they are pushed up to the Repo.

```console
$ prek install
prek installed at .git/hooks/pre-commit
```

This will ensure that all code meets the required linting standard before being
committed.

## Run checks manually

You can run these checks manually on all staged files using the below command :

```console
poe pre
```

## Testing

We are using [pytest](https://docs.pytest.org/) for testing. Tests will
automatically be run when you submit a pull request. You can also run them
manually using the following command:

```console
pytest
```

If you add any new features, please add tests for them. This will help us to
ensure that the code is working as expected and will prevent any regressions.

## Changelog

The changelog is automatically generated using
[github-changelog-md](https://changelog.seapagan.net), so please do not edit it
manually.

For maintainers, there is a POE task that will run this and update the changelog
file.

```console
poe changelog
```

You would also need to add a GitHub Personal Access Token to a local config file
as usual. See the section in that tools
[Documentation](https://changelog.seapagan.net/installation/#setup-a-github-pat)
for information.

**However, you should NOT include a change to the `CHANGELOG.md` file in any
Pull Requests. This will be handled by the maintainers when a new release is
made**. Your GitHub username will be added to the changelog automatically beside
your PR.

## Convenience Tasks

There are a few other convenience tasks that can be run using the `poe` command.
These are defined in the `pyproject.toml` file.

Each of these tasks can have extra options added which will be passed to the
underlying tool.

Run **`mypy`** on the code base in strict mode:

```console
poe mypy
```

Format the code using **`ruff format`**:

```console
poe format
```

Lint the code using **`ruff check`**:

```console
poe ruff
```

## Documentation Tasks

These are to help with developing and updating the documentation.

- `poe docs:serve` - Serve the MkDocs locally for testing and development
- `poe docs:serve:all` - Same as above, but opens to all interfaces so you can
  view it on other devices on your network
- `poe docs:build` - Build the MkDocs site into the `dist` folder
- `poe docs:publish` - Publish the docs to your GitHub pages. **Note that only
  those with write-access to this repo can do this**.

## Guidelines

Here are some guidelines to follow when contributing to Cogitus:

- Do not update the version number in the `pyproject.toml` file. This will be
  done by the maintainers when a new release is made.
- Follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide. The
  prek hooks will check for this. We are using
  [Ruff](https://docs.astral.sh/ruff/) as both a linter and code formatter.
- Try to have no linting errors or warnings. The prek hooks will check for
  this also.
- [MyPy](https://mypy.readthedocs.io/en/stable/) is installed and we are using
  type hints. Please try to add type hints to your code. If you see any areas of
  the code that are missing type hints, please feel free to open a PR and add
  them 😁!
- Write clear and concise commit messages.
- Write tests for your code.
- Make sure your code passes all tests before submitting a pull request.
- Document your code using
  [docstrings](https://www.python.org/dev/peps/pep-0257/).
- Use [GitHub issues](https://github.com/seapagan/cogitus/issues)
  to report bugs or suggest new features.

## Contact

If you have any questions or need help with contributing, please contact me
**@seapagan** on GitHub. You can also use the [GitHub
Discussions](https://github.com/seapagan/cogitus/discussions)
feature.

Happy contributing!
