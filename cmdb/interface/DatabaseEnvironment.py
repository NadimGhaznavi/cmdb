"""Read database credentials as data for maintenance commands."""

from pathlib import Path


class DatabaseEnvironment:
    @staticmethod
    def read(path: Path) -> dict[str, str]:
        values = {}
        for line in path.read_text().splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in values:
                raise ValueError("Invalid database environment file.")
            values[key] = value
        DatabaseEnvironment.validate(values)
        return values

    @staticmethod
    def validate(values: dict[str, str]) -> None:
        if values.keys() != {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"}:
            raise ValueError("Unexpected database environment fields.")
        if not all(values.values()) or not 1 <= int(values["DB_PORT"]) <= 65535:
            raise ValueError("Invalid database connection settings.")
