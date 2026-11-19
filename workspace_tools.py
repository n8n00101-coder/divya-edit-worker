"""Julie agent engine (E2.5 + E10): WORKSPACE FILE TOOLS.

E2's registry shipped with an honest gap: the runner had no file
read/list helper for a job workspace to wrap, so no file tool was
registered. E2.5 closes that gap with a small, purpose-built module
— the file primitives did not exist anywhere to wrap, so these are
new, but deliberately minimal and confined.

Four tools, registered by register_workspace_tools(reg, root):

  file_list    read-only   list one directory inside the workspace
  file_read    read-only   read one text file (byte-capped)
  file_write   mutating + needs Allow   write/replace one text file
  file_append  mutating + needs Allow   append to one text file

E10 adds four more tools:

  edit_file    mutating + needs Allow   surgical exact-match edit
  search_text  read-only   grep over the workspace
  list_files   read-only   glob over the workspace
  run_command  mutating + needs Allow   sandboxed command execution

CONFINEMENT (the whole point of the module): every path argument is
resolved against the per-job workspace ROOT the caller passes in,
and anything that lands outside that root is REFUSED as a FAILED
step — the handler never touches the filesystem outside the root.
Resolution uses os.path.realpath, so `..` segments, absolute paths
pointing elsewhere, and symlinks inside the root that point out are
all caught by the same check: the fully resolved target must be the
root itself or live under it. The check runs BEFORE any filesystem
operation (including the parent-directory creation file_write
performs), and file_read checks the resolved path again after
opening is not needed — realpath already resolved every symlink
component that exists. (Known limit, stated honestly: this is a
check-then-act sequence, so a hostile process racing to swap a
symlink between the check and the open could in theory slip past;
the runner is a single-job ephemeral process with no hostile local
actor, and no production flow registers these tools yet.)

Caps: file_read returns at most READ_CAP bytes of text with an
explicit truncation note when the file is larger; a file that looks
binary (NUL bytes, or not decodable as UTF-8) is refused with the
reason instead of being mangled into the brain's context.
file_write / file_append content is capped at WRITE_CAP bytes.
file_list returns at most LIST_CAP entries.
search_text returns at most SEARCH_CAP matches.
list_files returns at most LIST_FILES_CAP entries.
run_command has a default timeout and output cap.

Handlers follow the agent_loop tool contract: (ok, result) tuples;
a refusal is (False, reason) — a FAILED step the loop feeds back to
the brain, never an exception and never a silent no-op.
"""

import os
import re
import subprocess
import tempfile

READ_CAP = 64 * 1024        # max bytes file_read returns
WRITE_CAP = 256 * 1024      # max content bytes file_write/file_append take
LIST_CAP = 200              # max entries file_list returns
SEARCH_CAP = 100            # max matches search_text returns
LIST_FILES_CAP = 500        # max entries list_files returns
COMMAND_TIMEOUT = 30        # default timeout for run_command in seconds
COMMAND_OUTPUT_CAP = 64 * 1024  # max bytes run_command returns


def _confined(root_real, path_arg):
    """Resolve path_arg against root_real. Returns the absolute,
    symlink-resolved target path when it is the root or inside it,
    else None (the caller refuses). An absolute path_arg is honoured
    only when it too resolves inside the root."""
    p = str(path_arg or "")
    cand = p if os.path.isabs(p) else os.path.join(root_real, p)
    real = os.path.realpath(cand)
    if real == root_real:
        return real
    if real.startswith(root_real + os.sep):
        return real
    return None


def _refused(path_arg):
    return False, (f"REFUSED: path {path_arg!r} escapes the job "
                   f"workspace — file tools only work inside it")


def register_workspace_tools(reg, root, job_record=None):
    """Register the workspace file tools on `reg`, confined to
    `root` (the per-job workspace directory the caller owns; created
    here if missing). Mirrors tools_registry.register_browser_tools:
    handlers close over the context, classifications ride on the
    registry entries — reads are read-only, writes are mutating and
    need the user's Allow (the registry default for mutating).

    E10: job_record is used for read-before-edit enforcement.
    It should be a mutable dict-like object that persists across
    tool calls (the job record in agent_loop)."""
    root_real = os.path.realpath(str(root))
    os.makedirs(root_real, exist_ok=True)

    # Track files that have been read in this job (for read-before-edit)
    # This is stored on the job_record under key "_e10_files_read"
    def _mark_file_read(rel_path):
        if job_record is not None:
            read_set = job_record.setdefault("_e10_files_read", set())
            # Store the resolved relative path
            target = _confined(root_real, rel_path)
            if target:
                # Store the relative path from root
                try:
                    rel = os.path.relpath(target, root_real)
                    if rel != ".":
                        read_set.add(rel)
                except ValueError:
                    pass

    def _check_file_read(rel_path):
        """Check if file was read before in this job. Returns True if allowed."""
        if job_record is None:
            return True  # No enforcement if no job record
        read_set = job_record.get("_e10_files_read", set())
        target = _confined(root_real, rel_path)
        if not target:
            return False
        try:
            rel = os.path.relpath(target, root_real)
            if rel == ".":
                return False
            return rel in read_set
        except ValueError:
            return False

    def _list(args):
        rel = str(args.get("path") or ".")
        target = _confined(root_real, rel)
        if target is None:
            return _refused(rel)
        if not os.path.isdir(target):
            return False, f"not a directory: {rel!r}"
        try:
            names = sorted(os.listdir(target))
        except OSError as e:
            return False, f"list failed for {rel!r}: {e}"
        lines = [f"{rel} — {len(names)} entr"
                 f"{'y' if len(names) == 1 else 'ies'}"]
        for n in names[:LIST_CAP]:
            full = os.path.join(target, n)
            if os.path.isdir(full):
                lines.append(f"  {n}/")
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = -1
                lines.append(f"  {n} ({size} B)")
        if len(names) > LIST_CAP:
            lines.append(f"  … truncated at {LIST_CAP} entries")
        return True, "\n".join(lines)

    def _read(args):
        rel = str(args.get("path") or "")
        target = _confined(root_real, rel)
        if target is None:
            return _refused(rel)
        if not os.path.isfile(target):
            return False, f"not a file: {rel!r}"
        try:
            with open(target, "rb") as f:
                raw = f.read(READ_CAP + 1)
        except OSError as e:
            return False, f"read failed for {rel!r}: {e}"
        chunk = raw[:READ_CAP]
        if b"\x00" in chunk:
            return False, (f"refused: {rel!r} looks binary (NUL bytes) "
                           f"— file_read is for text files")
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            return False, (f"refused: {rel!r} is not valid UTF-8 text "
                           f"— file_read is for text files")
        if len(raw) > READ_CAP:
            text += (f"\n… [truncated: file is larger than the "
                     f"{READ_CAP}-byte read cap]")
        # Mark as read for read-before-edit enforcement
        _mark_file_read(rel)
        return True, text

    def _write(args, append):
        rel = str(args.get("path") or "")
        content = str(args.get("content") or "")
        data = content.encode("utf-8")
        if len(data) > WRITE_CAP:
            return False, (f"refused: content is {len(data)} bytes, "
                           f"over the {WRITE_CAP}-byte write cap")
        target = _confined(root_real, rel)
        if target is None or target == root_real:
            return _refused(rel)
        if os.path.isdir(target):
            return False, f"is a directory: {rel!r}"
        parent = os.path.dirname(target)
        try:
            os.makedirs(parent, exist_ok=True)
            # Track if file existed before this write
            file_existed = os.path.isfile(target)
            # Now write
            with open(target, "ab" if append else "wb") as f:
                f.write(data)
            # Mark in job_record that this file existed before this write
            # if job_record is available (from register_workspace_tools)
            if job_record is not None:
                existed_key = f"_e10_file_existed_before_{rel}"
                # Use setdefault to create if not exists
                job_record.setdefault(existed_key, file_existed)
        except OSError as e:
            return False, f"write failed for {rel!r}: {e}"
        verb = "appended" if append else "wrote"
        return True, f"{verb} {len(data)} bytes to {rel}"

    def _append(args):
        return _write(args, append=True)

    def _write_only(args):
        return _write(args, append=False)

    # E10: edit_file — surgical exact-match replacement
    def _edit(args):
        rel = str(args.get("path") or "")
        old_text = str(args.get("old_text") or "")
        new_text = str(args.get("new_text") or "")

        # Read-before-edit enforcement
        if not _check_file_read(rel):
            return False, (f"REFUSED: edit_file requires a prior file_read "
                           f"of {rel!r} in this job — read the file first")

        if not old_text:
            return False, "refused: old_text must not be empty"

        target = _confined(root_real, rel)
        if target is None or target == root_real:
            return _refused(rel)
        if not os.path.isfile(target):
            return False, f"not a file: {rel!r}"
        if os.path.isdir(target):
            return False, f"is a directory: {rel!r}"

        try:
            with open(target, "r", encoding="utf-8") as f:
                current = f.read()
        except OSError as e:
            return False, f"read failed for {rel!r}: {e}"
        except UnicodeDecodeError:
            return False, (f"refused: {rel!r} is not valid UTF-8 text "
                           f"— edit_file is for text files")

        # Exact match check
        count = current.count(old_text)
        if count == 0:
            return False, (f"refused: old_text not found in {rel!r} — "
                           f"exact match required (case-sensitive)")
        if count > 1:
            return False, (f"refused: old_text matches {count} times in "
                           f"{rel!r} — must be unique for surgical edit")

        # Replace exactly once
        new_content = current.replace(old_text, new_text, 1)
        new_data = new_content.encode("utf-8")
        if len(new_data) > WRITE_CAP:
            return False, (f"refused: result would be {len(new_data)} bytes, "
                           f"over the {WRITE_CAP}-byte write cap")

        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            return False, f"write failed for {rel!r}: {e}"

        return True, f"edited {rel} (1 occurrence replaced)"

    # E10: search_text — grep over workspace
    def _search(args):
        pattern = str(args.get("pattern") or "")
        glob_pattern = str(args.get("glob") or "**/*")

        if not pattern:
            return False, "refused: pattern must not be empty"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return False, f"invalid regex pattern: {e}"

        # Find files matching glob
        import glob as glob_mod
        search_glob = os.path.join(root_real, glob_pattern)
        matches = []
        try:
            for filepath in glob_mod.glob(search_glob, recursive=True):
                if not os.path.isfile(filepath):
                    continue
                # Check confinement
                real = os.path.realpath(filepath)
                if not (real == root_real or real.startswith(root_real + os.sep)):
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read(READ_CAP + 1)
                    if b"\x00" in content.encode("utf-8")[:READ_CAP]:
                        continue  # skip binary
                    # Search line by line for context
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if regex.search(line):
                            rel = os.path.relpath(filepath, root_real)
                            if rel == ".":
                                rel = os.path.basename(filepath)
                            matches.append(f"{rel}:{i+1}:{line[:200]}")
                            if len(matches) >= SEARCH_CAP:
                                break
                    if len(matches) >= SEARCH_CAP:
                        break
                except (OSError, UnicodeDecodeError):
                    continue
        except Exception as e:
            return False, f"search failed: {e}"

        if not matches:
            return True, f"No matches for pattern {pattern!r} in {glob_pattern!r}"
        lines = [f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} "
                 f"for {pattern!r} in {glob_pattern!r}:"]
        lines.extend(matches)
        if len(matches) >= SEARCH_CAP:
            lines.append(f"… truncated at {SEARCH_CAP} matches")
        return True, "\n".join(lines)

    # E10: list_files — glob over workspace
    def _list_files(args):
        glob_pattern = str(args.get("glob") or "**/*")

        import glob as glob_mod
        search_glob = os.path.join(root_real, glob_pattern)
        results = []
        try:
            for filepath in glob_mod.glob(search_glob, recursive=True):
                if not (os.path.isfile(filepath) or os.path.isdir(filepath)):
                    continue
                real = os.path.realpath(filepath)
                if not (real == root_real or real.startswith(root_real + os.sep)):
                    continue
                rel = os.path.relpath(filepath, root_real)
                if rel == ".":
                    continue
                if os.path.isdir(filepath):
                    results.append(rel + "/")
                else:
                    try:
                        size = os.path.getsize(filepath)
                    except OSError:
                        size = -1
                    results.append(f"{rel} ({size} B)")
                if len(results) >= LIST_FILES_CAP:
                    break
        except Exception as e:
            return False, f"list_files failed: {e}"

        results.sort()
        lines = [f"Files matching {glob_pattern!r} in workspace:"]
        lines.extend(results)
        if len(results) >= LIST_FILES_CAP:
            lines.append(f"… truncated at {LIST_FILES_CAP} entries")
        elif not results:
            lines.append("  (no matches)")
        return True, "\n".join(lines)

    # E10: run_command — sandboxed command execution
    def _run_command(args):
        cmd = args.get("cmd")
        if not cmd:
            return False, "refused: cmd must not be empty"
        if isinstance(cmd, list):
            # List form: ["cmd", "arg1", "arg2"]
            pass
        elif isinstance(cmd, str):
            # String form: split but be careful
            import shlex
            cmd = shlex.split(cmd)
        else:
            return False, "refused: cmd must be string or list"

        # Sandbox contract (honest): the working directory is the
        # workspace root, with a timeout and an output cap. This is
        # NOT filesystem confinement — the command itself is the
        # brain's, which is why run_command is mutating + needs
        # Allow, and why the production agent runner does not
        # auto-Allow it (see agent_runner.SANDBOX_ALLOW).
        try:
            timeout = int(args.get("timeout", COMMAND_TIMEOUT))
        except (TypeError, ValueError):
            return False, "refused: timeout must be a number of seconds"
        timeout = max(1, min(timeout, 300))  # clamp 1-300 seconds

        try:
            proc = subprocess.run(
                cmd,
                cwd=root_real,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PWD": root_real}
            )
        except subprocess.TimeoutExpired:
            return False, f"command timed out after {timeout}s"
        except Exception as e:
            return False, f"command failed to start: {e}"

        output = proc.stdout + proc.stderr
        if len(output) > COMMAND_OUTPUT_CAP:
            output = output[:COMMAND_OUTPUT_CAP] + f"\n… [truncated at {COMMAND_OUTPUT_CAP} bytes]"

        if proc.returncode == 0:
            return True, output if output else "(no output)"
        else:
            return False, f"exit {proc.returncode}: {output}"

    reg.register(
        "file_list",
        "List files in a workspace directory (default the workspace root). Args: {path?}. Read-only.",
        {"path": {"type": "string", "required": False,
                  "desc": "directory path inside the workspace"}},
        _list, timeout=15)
    reg.register(
        "file_read",
        "Read a text file in the workspace (capped, binary refused). Args: {path}. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "file path inside the workspace"}},
        _read, timeout=15)
    reg.register(
        "file_write",
        "Write (replace) a text file in the workspace, creating parent folders. Args: {path, content}.",
        {"path": {"type": "string", "required": True,
                  "desc": "file path inside the workspace"},
         "content": {"type": "string", "required": True,
                     "desc": "the full text content to write"}},
        _write_only, mutating=True, timeout=15)
    reg.register(
        "file_append",
        "Append text to a file in the workspace (created if missing). Args: {path, content}.",
        {"path": {"type": "string", "required": True,
                  "desc": "file path inside the workspace"},
         "content": {"type": "string", "required": True,
                     "desc": "the text to append"}},
        _append, mutating=True, timeout=15)
    # E10 tools
    reg.register(
        "edit_file",
        "Surgical exact-match edit of a text file in the workspace. Requires a prior file_read of the same file in this job. Args: {path, old_text, new_text}.",
        {"path": {"type": "string", "required": True,
                  "desc": "file path inside the workspace"},
         "old_text": {"type": "string", "required": True,
                      "desc": "exact text to replace (must match once)"},
         "new_text": {"type": "string", "required": True,
                      "desc": "replacement text"}},
        _edit, mutating=True, timeout=15)
    reg.register(
        "search_text",
        "Search (grep) for a regex pattern in files under the workspace. Args: {pattern, glob?}. Read-only.",
        {"pattern": {"type": "string", "required": True,
                     "desc": "regex pattern to search for"},
         "glob": {"type": "string", "required": False,
                  "desc": "glob pattern for files to search (default **/*)"}},
        _search, timeout=30)
    reg.register(
        "list_files",
        "List files matching a glob pattern in the workspace. Args: {glob?}. Read-only.",
        {"glob": {"type": "string", "required": False,
                  "desc": "glob pattern (default **/*)"}},
        _list_files, timeout=15)
    reg.register(
        "run_command",
        "Run a shell command sandboxed to the workspace directory. Args: {cmd, timeout?}. Mutating, needs Allow.",
        {"cmd": {"type": ["string", "array"], "required": True,
                 "desc": "command to run (string or list of args)"},
         "timeout": {"type": "number", "required": False,
                     "desc": "timeout in seconds (default 30, max 300)"}},
        _run_command, mutating=True, timeout=60)

    return reg