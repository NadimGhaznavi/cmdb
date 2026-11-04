"""Database factory doubles with the canonical connection context lifetime."""

from unittest.mock import MagicMock, Mock


def database_factory(**kwargs):
    factory = Mock(**kwargs)
    connection = factory.return_value = MagicMock()
    connection.__enter__.return_value = connection

    def close(*args):
        connection.close()
        return False

    connection.__exit__.side_effect = close
    return factory
