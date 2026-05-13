from pathlib import Path


def test_env_secret_files_are_ignored_by_project_patterns() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore


def test_env_example_contains_only_placeholder_values() -> None:
    env_example = Path(".env.example")
    rows = [
        line
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert rows == [
        "YOUTUBETRANSCRIPT_DEV_API_KEY=",
        "TRANSCRIPTAPI_KEY=",
        "YOUTUBE_API_KEY=",
        "APIFY_TOKEN=",
    ]
