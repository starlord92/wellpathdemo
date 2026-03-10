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
    if isinstance(content_type, str):
        content_type = content_type.encode("utf-8", errors="replace")
    if isinstance(body, str):
        body = body.encode("utf-8", errors="replace")
    # Extract boundary
    m = re.search(rb"boundary\s*=\s*([^\s;]+)", content_type, re.I)
    if not m:
        return None, None
    boundary = m.group(1).strip(b'"\' \t\r\n')
    if not boundary:
        return None, None
    # Split into parts (first part is preamble before first boundary)
    sep = b"\r\n--" + boundary
    parts = body.split(sep)
    for i, part in enumerate(parts):
        if i == 0:
            if part.strip().startswith(b"--"):
                continue
            part = part.lstrip(b"\r\n")
        if part.endswith(b"--\r\n") or part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        if not part:
            continue
        head_sep = part.find(b"\r\n\r\n")
        if head_sep == -1:
            head_sep = part.find(b"\n\n")
        if head_sep == -1:
            continue
        raw_headers = part[:head_sep]
        content = part[head_sep + 4:].rstrip(b"\r\n") if head_sep != -1 else b""
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
            fn = filename.decode("utf-8", errors="replace") if isinstance(filename, bytes) else (filename or "upload.bin")
            return bytes(content), fn
    return None, None
