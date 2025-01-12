# IAI Project Template

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![Coverage Badge](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/vinaysetty/1cc32e6b43d911995bf07adb1cce4e89/raw/coverage.template-project.main.json)

This repository serves as a template for software projects.

# Testing and GitHub actions

Using `pre-commit` hooks, `flake8`, `black`, `mypy`, `docformatter`, `pydocstyle` and `pytest` are locally run on every commit. For more details on how to use `pre-commit` hooks see [here](https://github.com/iai-group/guidelines/tree/main/python#install-pre-commit-hooks).

Similarly, Github actions are used to run `flake8`, `black`, `mypy`, `docformatter`, `pydocstyle` and `pytest` on every push and pull request and merge to main. The `pytest` also runs coverage. GitHub actions are explained in detail [here](https://github.com/iai-group/guidelines/blob/main/github/Actions.md).

For GitHub actions/CI Setup see [here](docs/CI_setup.md)