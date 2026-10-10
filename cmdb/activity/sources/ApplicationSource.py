"""Read installed application metadata without executing its constants."""

import ast
from pathlib import PurePosixPath
import re
import shlex
import subprocess

from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.entity.TaggedValue import TaggedValue
from cmdb.interface.SSH import SSH


def application_metadata(source: str) -> SoftwareSystem | None:
    """Read optional CMDB fields and a required literal VERSION."""
    try:
        module = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    statements = list(module.body)
    fields = {}
    names = {'VERSION': 'version', 'CMDB_TYPE': 'type', 'CMDB_SUBTYPE': 'subtype',
             'CMDB_SUPPLIER': 'supplier', 'CMDB_CODENAME': 'codename'}
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            statements.extend(statement.body)
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in names:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literal = value.value.strip()
                    if literal and len(literal) <= 255 and not any(
                            ord(character) < 32 or ord(character) == 127 for character in literal):
                        fields.setdefault(names[target.id], literal)
    if 'version' not in fields:
        return None
    codename = fields.pop('codename', None)
    system = SoftwareSystem(**fields)
    if codename is not None:
        system.taggedValue.append(TaggedValue(tag='VERSION_CODENAME', value=codename))
    return system


def application_pairs(source: str, field: str, limit: int) -> tuple[tuple[str, str], ...]:
    """Read validated literal name/value pairs without executing code."""
    try:
        module = ast.parse(source)
    except (SyntaxError, ValueError):
        return ()
    statements = list(module.body)
    components = []
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            statements.extend(statement.body)
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if not any(isinstance(target, ast.Name) and target.id == field for target in targets):
            continue
        try:
            declarations = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError, RecursionError):
            continue
        if not isinstance(declarations, (tuple, list)):
            continue
        for entry in declarations:
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                continue
            if not all(isinstance(item, str) and item.strip() and not any(
                    ord(character) < 32 or ord(character) == 127 for character in item) for item in entry):
                continue
            name, path = (item.strip() for item in entry)
            if len(name) > 255 or len(path) > limit:
                continue
            component = (name, path)
            if component not in components:
                components.append(component)
    return tuple(components)


def application_components(source: str) -> tuple[tuple[str, str], ...]:
    """Read filesystem components whose paths stay beneath the application root."""
    return tuple(dict.fromkeys((name, str(PurePosixPath(path)))
                 for name, path in application_pairs(source, 'CMDB_COMPONENTS', 4096)
                 if '..' not in PurePosixPath(path).parts and str(PurePosixPath(path)) != '.'))


def application_databases(source: str) -> tuple[tuple[str, str], ...]:
    """Read application labels and exact MariaDB catalog names."""
    return application_pairs(source, 'CMDB_DATABASES', 64)


def application_version(source: str) -> str | None:
    """Return the version from an application's literal metadata."""
    system = application_metadata(source)
    return system.version if system is not None else None


class ApplicationSource:
    def __init__(self) -> None:
        self._ssh = SSH()

    def collect(self, address: str, name: str) -> tuple[
            str, str | None, SoftwareSystem | None, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        """Return outcome, install path, metadata, filesystem components and database declarations."""
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) is None:
            return 'unsupported name', None, None, (), ()
        pathname = str(PurePosixPath(DCMDB.BASE_INSTALL_DIR) / name.lower())
        constants = str(PurePosixPath(pathname) / name.lower() / 'constants' / ('D' + name + '.py'))
        command = (f'if [ -d {shlex.quote(pathname)} ] && [ -f {shlex.quote(constants)} ]; '
                   f'then cat -- {shlex.quote(constants)}; fi')
        try:
            result = self._ssh.run(address, command, timeout=DCMDB.SSH_COMMAND_TIMEOUT_SECONDS,
                                   connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            return 'read failed', pathname, None, (), ()
        system = application_metadata(result.stdout)
        components = application_components(result.stdout) if system is not None else ()
        databases = application_databases(result.stdout) if system is not None else ()
        return ('observed' if system is not None else 'not detected'), pathname, system, components, databases
