"""Check relative Markdown/HTML link targets in README and tracked documentation.

Code examples, external URLs and same-document fragments are excluded. Targets must
exist and be tracked, so ignored local artifacts cannot hide a broken public link.
"""
from pathlib import Path
import json
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    tracked = set(subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT).decode('utf8').split('\0')) - {''}
    documents = sorted(p for p in tracked if p in {'README.md', 'README_DETAILED.md'} or
                       (p.startswith('docs/') and p.endswith(('.md', '.html'))))
    checked, broken = 0, []
    patterns = [r'!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)',
                r'^\s*\[[^\]\n]+\]:\s*(<[^>]+>|\S+)',
                r'(?:href|src)\s*=\s*[\"\']([^\"\']+)[\"\']']
    for name in documents:
        text = (ROOT / name).read_text(encoding='utf8')
        # Keep line numbers stable while removing fenced and inline code.
        text = re.sub(r'^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1[^\n]*$',
                      lambda m: '\n' * m[0].count('\n'), text, flags=re.M | re.S)
        text = re.sub(r'`[^`\n]+`', lambda m: ' ' * len(m[0]), text)
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.M | re.I):
                url = match[1].strip('<>')
                parts = urlsplit(url)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                checked += 1
                path = unquote(parts.path)
                target = ((ROOT / path.lstrip('/')) if path.startswith('/') else
                          (ROOT / name).parent / path).resolve()
                try:
                    relative = target.relative_to(ROOT).as_posix()
                except ValueError:
                    relative = ''
                in_index = relative in tracked or (target.is_dir() and any(
                    p.startswith(relative.rstrip('/') + '/') for p in tracked))
                if not target.exists() or not in_index:
                    broken.append({'file': name, 'line': text.count('\n', 0, match.start()) + 1,
                                   'target': url})
    print(json.dumps({'documents': len(documents), 'relative_links': checked,
                      'broken': broken}, indent=2))
    return bool(broken)


if __name__ == '__main__':
    raise SystemExit(main())
