"""
Shared multipart/form-data parser for Vercel Python APIs.
Uses manual boundary parsing so it works when cgi.FieldStorage fails (e.g. on Vercel).
"""
import re


def parse_multipart(content_type, body, field_names):
    """
    Parse multipart/form-data body. Returns (file_bytes, filename) or (None, None).
    field_names: tuple of accepted form field names, e.g. ("file", "document").
    """
    ct = content_type or ""
    if not ct or "multipart/form-data" not in ct.lower():
        return None, None
    if not body:
        return None, None
    ct_bytes = ct.encode("utf-8", errors="replace") if isinstance(ct, str) else ct
    if isinstance(body, str):
        body = body.encode("utf-8", errors="replace")
    # Extract boundary (preserve original case — boundary values are case-sensitive)
    m = re.search(rb"boundary\s*=\s*([^\s;]+)", ct_bytes, re.I)
    if not m:
        return None, None
    boundary = m.group(1).strip(b'"\' \t\r\n')
    if not boundary:
        return None, None

    delim = b"--" + boundary

    # Find the opening delimiter in the body
    start = body.find(delim)
    if start == -1:
        return None, None

    # Skip past the opening delimiter line (delim + \r\n or \n)
    pos = start + len(delim)
    if body[pos:pos + 2] == b"\r\n":
        pos += 2
    elif body[pos:pos + 1] == b"\n":
        pos += 1
    else:
        return None, None  # malformed

    # Split the remaining body into parts on \r\n + delim
    rest = body[pos:]
    parts = rest.split(b"\r\n" + delim)

    for part in parts:
        # Strip closing boundary marker suffix (-- or --\r\n)
        if part.endswith(b"--\r\n"):
            part = part[:-4]
        elif part.endswith(b"--"):
            part = part[:-2]
        if not part:
            continue

        # Split headers from body content
        head_sep = part.find(b"\r\n\r\n")
        if head_sep == -1:
            head_sep = part.find(b"\n\n")
            if head_sep == -1:
                continue
            raw_headers = part[:head_sep]
            content = part[head_sep + 2:].rstrip(b"\r\n")
        else:
            raw_headers = part[:head_sep]
            content = part[head_sep + 4:].rstrip(b"\r\n")

        # Parse Content-Disposition for name and filename
        disp = None
        for line in raw_headers.split(b"\n"):
            line = line.strip(b"\r\n ")
            if line.lower().startswith(b"content-disposition:"):
                disp = line
                break
        if not disp:
            continue
        name = None
        filename = None
        for token in re.split(rb";\s*", disp, flags=re.I):
            token = token.strip()
            if token.lower().startswith(b"name="):
                name = token[5:].strip(b'"\' ')
            elif token.lower().startswith(b"filename="):
                filename = token[9:].strip(b'"\' ')
        if name is None:
            continue
        try:
            name = name.decode("utf-8", errors="replace")
        except Exception:
            pass
        if filename is not None:
            try:
                filename = filename.decode("utf-8", errors="replace")
            except Exception:
                filename = "upload.bin"
        if name in field_names and content:
            fn = filename if isinstance(filename, str) else (filename.decode("utf-8", errors="replace") if filename else "upload.bin")
            return bytes(content), fn
    return None, None
