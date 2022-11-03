import re

import click

def t(level):
    return "  " * level

def delete_term_n_previous_line(n):
    for i in range(n):
        click.get_text_stream('stdout').write('\033[A\r\033[K')

def extract_info_from_conan_ref(conan_ref):
    match = re.search(r'(\w+)\/([^@]+)(@(\w+)\/(\w+)#?(\w+)?)?', conan_ref)
    if len(match.groups()) == 3:
        return (
            match.group(1),
            match.group(2),
            "", "", ""
        )
    if len(match.groups()) == 6:
        return (
            match.group(1),
            match.group(2),
            match.group(4),
            match.group(5),
            "",
        )

    return (
        match.group(1),
        match.group(2),
        match.group(4),
        match.group(5),
        match.group(6),
    )
