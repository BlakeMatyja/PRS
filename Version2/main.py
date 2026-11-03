"""Entry point for the PRS (Version 2)."""
from prs.app import PRSApplication
from prs.cli import PRSConsole


def main() -> None:
    """Start the command-line PRS using prs.db in the current folder."""
    PRSConsole(PRSApplication()).run()


if __name__ == "__main__":
    main()
