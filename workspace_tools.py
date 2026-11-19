"""Julie agent engine (E2.5): WORKSPACE FILE TOOLS.

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

Handlers follow the agent_loop tool contract: (ok, result) tuples;
a refusal is (False, reason) — a FAILED step the loop feeds back to
the brain, never an exception and never a silent no-op.
"""

import os

READ_CAP = 64 * 1024        # max bytes file_read returns
WRITE_CAP = 256 * 1024      # max content bytes file_write/file_append take
LIST_CAP = 200              # max entries file_list returns


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


def register_workspace_tools(reg, root):
    """Register the four workspace file tools on `reg`, confined to
    `root` (the per-job workspace directory the caller owns; created
    here if missing). Mirrors tools_registry.register_browser_tools:
    handlers close over the context, classifications ride on the
    registry entries — reads are read-only, writes are mutating and
    need the user's Allow (the registry default for mutating)."""
    root_real = os.path.realpath(str(root))
    os.makedirs(root_real, exist_ok=True)

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
        # The parent chain must stay confined too: _confined already
        # resolved the full target (realpath resolves every existing
        # symlink component), so a symlinked parent pointing out was
        # refused above. Create only inside the root.
        try:
            os.makedirs(parent, exist_ok=True)
            with open(target, "ab" if append else "wb") as f:
                f.write(data)
        except OSError as e:
            return False, f"write failed for {rel!r}: {e}"
        verb = "appended" if append else "wrote"
        return True, f"{verb} {len(data)} bytes to {rel}"

    def _append(args):
        return _write(args, append=True)

    def _write_only(args):
        return _write(args, append=False)

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
    return reg
