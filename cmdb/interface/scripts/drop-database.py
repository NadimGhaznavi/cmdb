"""Drop one explicitly selected user database through the local MariaDB socket."""

import subprocess
import sys


def main():
    if len(sys.argv) != 2:
        raise ValueError('Provide one database name.')
    name = sys.argv[1]
    if (not name or len(name) > 64 or '\0' in name
            or name.lower() in ('cmdb', 'mysql', 'information_schema', 'performance_schema', 'sys')):
        raise ValueError('This database cannot be deleted.')
    identifier = name.replace('`', '``')
    subprocess.run(['mariadb', '--no-defaults', '--protocol=socket', '--skip-ssl',
                    '--user=root', '--batch', '--binary-mode'],
                   input=f'DROP DATABASE IF EXISTS `{identifier}`;\n', text=True, check=True, timeout=30)


if __name__ == '__main__':
    main()
