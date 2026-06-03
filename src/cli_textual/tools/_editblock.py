"""Forgiving search-and-replace matching for the ``edit_file`` tool.

The functions in this module are ported (lightly adapted) from Aider's
``aider/coders/editblock_coder.py``:

    https://github.com/Aider-AI/aider  —  Copyright (c) Paul Gauthier
    Licensed under the Apache License, Version 2.0.

We borrow only Aider's *matching* layer — given an ``old`` chunk and a ``new``
chunk, locate ``old`` in the file content even when it differs by leading
whitespace or elides lines with ``...`` — not its prose edit-format parser.
cli-textual is a tool-calling agent, so the model supplies ``old``/``new`` as
structured tool arguments; this module just makes the replacement robust so a
small whitespace drift doesn't fail the edit. See ../../../NOTICE.

Faithful to Aider's *active* escalation path (it deliberately stops before the
edit-distance fallback): perfect match → whitespace-flexible → drop spurious
leading blank line → ``...`` elision handling. No third-party dependencies.
"""
import re


def prep(content):
    if content and not content.endswith("\n"):
        content += "\n"
    lines = content.splitlines(keepends=True)
    return content, lines


def perfect_replace(whole_lines, part_lines, replace_lines):
    part_tup = tuple(part_lines)
    part_len = len(part_lines)

    for i in range(len(whole_lines) - part_len + 1):
        whole_tup = tuple(whole_lines[i : i + part_len])
        if part_tup == whole_tup:
            res = whole_lines[:i] + replace_lines + whole_lines[i + part_len :]
            return "".join(res)


def match_but_for_leading_whitespace(whole_lines, part_lines):
    num = len(whole_lines)

    # does the non-whitespace all agree?
    if not all(whole_lines[i].lstrip() == part_lines[i].lstrip() for i in range(num)):
        return

    # are they all offset the same?
    add = set(
        whole_lines[i][: len(whole_lines[i]) - len(part_lines[i])]
        for i in range(num)
        if whole_lines[i].strip()
    )

    if len(add) != 1:
        return

    return add.pop()


def replace_part_with_missing_leading_whitespace(whole_lines, part_lines, replace_lines):
    # Models often mess up leading whitespace, usually uniformly across the
    # old and new blocks — omitting all of it, or only some.
    #
    # Known limitation: this returns the FIRST indentation-tolerant match rather
    # than detecting multiple ambiguous matches. It's reached only as a fallback
    # in edit_file when exact matching already found zero hits (the exact-match
    # uniqueness guard runs first), and it mirrors Aider's upstream behavior.
    # Tightening it to surface "multiple forgiving matches" is a future enhancement.

    # Outdent everything by the max fixed amount possible.
    leading = [len(p) - len(p.lstrip()) for p in part_lines if p.strip()] + [
        len(p) - len(p.lstrip()) for p in replace_lines if p.strip()
    ]

    if leading and min(leading):
        num_leading = min(leading)
        part_lines = [p[num_leading:] if p.strip() else p for p in part_lines]
        replace_lines = [p[num_leading:] if p.strip() else p for p in replace_lines]

    # can we find an exact match not including the leading whitespace?
    num_part_lines = len(part_lines)

    for i in range(len(whole_lines) - num_part_lines + 1):
        add_leading = match_but_for_leading_whitespace(
            whole_lines[i : i + num_part_lines], part_lines
        )

        if add_leading is None:
            continue

        replace_lines = [add_leading + rline if rline.strip() else rline for rline in replace_lines]
        whole_lines = whole_lines[:i] + replace_lines + whole_lines[i + num_part_lines :]
        return "".join(whole_lines)

    return None


def perfect_or_whitespace(whole_lines, part_lines, replace_lines):
    # Try for a perfect match
    res = perfect_replace(whole_lines, part_lines, replace_lines)
    if res:
        return res

    # Try being flexible about leading whitespace
    res = replace_part_with_missing_leading_whitespace(whole_lines, part_lines, replace_lines)
    if res:
        return res


def try_dotdotdots(whole, part, replace):
    """Handle edits whose ``old``/``new`` chunks elide lines with ``...``.

    Returns the updated content, or ``None`` if there are no ``...`` lines.
    Raises ``ValueError`` if the ``...`` markers don't pair up or match.
    """
    dots_re = re.compile(r"(^\s*\.\.\.\n)", re.MULTILINE | re.DOTALL)

    part_pieces = re.split(dots_re, part)
    replace_pieces = re.split(dots_re, replace)

    if len(part_pieces) != len(replace_pieces):
        raise ValueError("Unpaired ... in edit block")

    if len(part_pieces) == 1:
        # no dots in this edit block, just return None
        return

    # Compare the ... separators (odd indices) in both
    all_dots_match = all(part_pieces[i] == replace_pieces[i] for i in range(1, len(part_pieces), 2))

    if not all_dots_match:
        raise ValueError("Unmatched ... in edit block")

    part_pieces = [part_pieces[i] for i in range(0, len(part_pieces), 2)]
    replace_pieces = [replace_pieces[i] for i in range(0, len(replace_pieces), 2)]

    pairs = zip(part_pieces, replace_pieces)
    for part, replace in pairs:
        if not part and not replace:
            continue

        if not part and replace:
            if not whole.endswith("\n"):
                whole += "\n"
            whole += replace
            continue

        if whole.count(part) == 0:
            raise ValueError
        if whole.count(part) > 1:
            raise ValueError

        whole = whole.replace(part, replace, 1)

    return whole


def replace_most_similar_chunk(whole, part, replace):
    """Best effort to find ``part`` in ``whole`` and replace it with ``replace``.

    Returns the updated content, or ``None`` if no acceptable match was found.
    """
    whole, whole_lines = prep(whole)
    part, part_lines = prep(part)
    replace, replace_lines = prep(replace)

    res = perfect_or_whitespace(whole_lines, part_lines, replace_lines)
    if res:
        return res

    # drop a spurious leading blank line that models sometimes add
    if len(part_lines) > 2 and not part_lines[0].strip():
        skip_blank_line_part_lines = part_lines[1:]
        res = perfect_or_whitespace(whole_lines, skip_blank_line_part_lines, replace_lines)
        if res:
            return res

    # handle elision with ...
    try:
        res = try_dotdotdots(whole, part, replace)
        if res:
            return res
    except ValueError:
        pass

    return None
