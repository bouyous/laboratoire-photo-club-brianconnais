# PhotoLabPro code reused for the club at the authorizing project owner’s request, 2026-10-13. MIT OR Apache-2.0.
"""Decode Windows command output without reader-thread Unicode errors."""
import locale


def decode_system_output(raw):
    if isinstance(raw,str):return raw
    raw=raw or b''
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):return raw.decode('utf-16',errors='replace')
    if b'\x00' in raw[:100]:return raw.decode('utf-16-le',errors='replace')
    try:return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        encoding=locale.getpreferredencoding(False)
        if encoding.lower().replace('-','') in ('utf8','utf8sig'):encoding='cp1252'
        return raw.decode(encoding,errors='replace')
