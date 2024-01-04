from os import environ
from os.path import commonpath
from pathlib import PurePath, Path
from typing import List, Dict, Any, Union, Tuple
from .loggers import logger, start_log_group

#: A path to generated cache artifacts. (only used when verbosity is in debug mode)
CACHE_PATH = Path(environ.get("CPP_LINTER_CACHE", ".cpp-linter_cache"))


class FileObj:
    """A class to represent a single file being analyzed.

    :param name: The file name. This should use Unix style path delimiters (``/``),
        even on Windows.
    :param additions: A `list` of line numbers that have added changes in the diff.
        This value is used to populate the `lines_added` property.
    :param diff_chunks: The ranges that define the beginning and ending line numbers
        for all hunks in the diff.
    """

    def __init__(self, name: str, additions: List[int], diff_chunks: List[List[int]]):
        self.name: str = name  #: The file name
        self.additions: List[int] = additions
        """A list of line numbers that contain added changes. This will be empty if
        not focusing on lines changed only."""
        self.diff_chunks: List[List[int]] = diff_chunks
        """A list of line numbers that define the beginning and ending of hunks in the
        diff. This will be empty if not focusing on lines changed only."""
        self.lines_added: List[List[int]] = FileObj._consolidate_list_to_ranges(
            additions
        )
        """A list of line numbers that define the beginning and ending of ranges that
        have added changes. This will be empty if not focusing on lines changed only.
        """

    @staticmethod
    def _consolidate_list_to_ranges(numbers: List[int]) -> List[List[int]]:
        """A helper function that is only used after parsing the lines from a diff that
        contain additions.

        :param numbers: A `list` of integers representing the lines' numbers that
            contain additions.
        :returns: A consolidated sequence of lists. Each list will have 2 items
            describing the starting and ending lines of all line ``numbers``.
        """
        result: List[List[int]] = []
        for i, n in enumerate(numbers):
            if not i:
                result.append([n])
            elif n - 1 != numbers[i - 1]:
                result[-1].append(numbers[i - 1] + 1)
                result.append([n])
            if i == len(numbers) - 1:
                result[-1].append(n + 1)
        return result

    def range_of_changed_lines(
        self, lines_changed_only: int, get_ranges: bool = False
    ) -> Union[List[int], List[List[int]]]:
        """Assemble a list of lines changed.

        :param lines_changed_only: A flag to indicate the focus of certain lines.

            - ``0``: focuses on all lines in a file(s).
            - ``1``: focuses on any lines shown in the event's diff (may include
              unchanged lines).
            - ``2``: focuses strictly on lines in the diff that contain additions.
        :param get_ranges: A flag to return a list of sequences representing
            :py:class:`range` parameters. Defaults to `False` since this is only
            required when constructing clang-tidy or clang-format CLI arguments.
        :returns:
            A list of line numbers for which to give attention. If ``get_ranges`` is
            asserted, then the returned list will be a list of ranges. If
            ``lines_changed_only`` is ``0``, then an empty list is returned.
        """
        if lines_changed_only:
            ranges = self.diff_chunks if lines_changed_only == 1 else self.lines_added
            if get_ranges:
                return ranges
            return self.additions
        # we return an empty list (instead of None) here so we can still iterate it
        return []  # type: ignore[return-value]

    def serialize(self) -> Dict[str, Any]:
        """For easy debugging, use this method to serialize the `FileObj` into a json
        compatible `dict`."""
        return {
            "filename": self.name,
            "line_filter": {
                "diff_chunks": self.diff_chunks,
                "lines_added": self.lines_added,
            },
        }


def is_file_in_list(paths: List[str], file_name: str, prompt: str) -> bool:
    """Determine if a file is specified in a list of paths and/or filenames.

    :param paths: A list of specified paths to compare with. This list can contain a
        specified file, but the file's path must be included as part of the
        filename.
    :param file_name: The file's path & name being sought in the ``paths`` list.
    :param prompt: A debugging prompt to use when the path is found in the list.

    :returns:

        - True if ``file_name`` is in the ``paths`` list.
        - False if ``file_name`` is not in the ``paths`` list.
    """
    for path in paths:
        result = commonpath([PurePath(path).as_posix(), PurePath(file_name).as_posix()])
        if result.replace("\\", "/") == path:
            logger.debug(
                '"./%s" is %s as specified in the domain "./%s"',
                file_name,
                prompt,
                path,
            )
            return True
    return False


def has_line_changes(
    lines_changed_only: int, diff_chunks: List[List[int]], additions: List[int]
) -> bool:
    """Does this file actually apply to condition specified by ``lines_changed_only``?

    :param lines_changed_only: A value that means:

        - 0 = We don't care. Analyze the whole file.
        - 1 = Only analyze lines in the diff chunks, which may include unchanged
          lines but not lines with subtractions.
        - 2 = Only analyze lines with additions.
    :param diff_chunks: The ranges of lines in the diff for a single file.
    :param additions: The lines with additions in the diff for a single file.
    """
    return (
        (lines_changed_only == 1 and len(diff_chunks) > 0)
        or (lines_changed_only == 2 and len(additions) > 0)
        or not lines_changed_only
    )


def is_source_or_ignored(
    file_name: str,
    ext_list: List[str],
    ignored: List[str],
    not_ignored: List[str],
):
    """Exclude undesired files (specified by user input :std:option:`--extensions`).
    This filtering is applied to the :attr:`~cpp_linter.Globals.FILES` attribute.

    :param file_name: The name of file in question.
    :param ext_list: A list of file extensions that are to be examined.
    :param ignored: A list of paths to explicitly ignore.
    :param not_ignored: A list of paths to explicitly not ignore.

    :returns:
        True if there are files to check. False will invoke a early exit (in
        `main()`) when no files to be checked.
    """
    return PurePath(file_name).suffix.lstrip(".") in ext_list and (
        is_file_in_list(not_ignored, file_name, "not ignored")
        or not is_file_in_list(ignored, file_name, "ignored")
    )


def list_source_files(
    extensions: List[str], ignored: List[str], not_ignored: List[str]
) -> List[FileObj]:
    """Make a list of source files to be checked. The resulting list is stored in
    :attr:`~cpp_linter.Globals.FILES`.

    :param extensions: A list of file extensions that should by attended.
    :param ignored: A list of paths to explicitly ignore.
    :param not_ignored: A list of paths to explicitly not ignore.

    :returns:
        True if there are files to check. False will invoke a early exit (in
        `main()` when no files to be checked.
    """
    start_log_group("Get list of specified source files")

    root_path = Path(".")
    files = []
    for ext in extensions:
        for rel_path in root_path.rglob(f"*.{ext}"):
            for parent in rel_path.parts[:-1]:
                if parent.startswith("."):
                    break
            else:
                file_path = rel_path.as_posix()
                logger.debug('"./%s" is a source code file', file_path)
                if is_file_in_list(
                    not_ignored, file_path, "not ignored"
                ) or not is_file_in_list(ignored, file_path, "ignored"):
                    files.append(FileObj(file_path, [], []))
    return files


def get_line_cnt_from_cols(file_path: str, offset: int) -> Tuple[int, int]:
    """Gets a line count and columns offset from a file's absolute offset.

    :param file_path: Path to file.
    :param offset: The byte offset to translate

    :returns:
        A `tuple` of 2 `int` numbers:

        - Index 0 is the line number for the given offset.
        - Index 1 is the column number for the given offset on the line.
    """
    # logger.debug("Getting line count from %s at offset %d", file_path, offset)
    contents = Path(file_path).read_bytes()[:offset]
    return (contents.count(b"\n") + 1, offset - contents.rfind(b"\n"))
