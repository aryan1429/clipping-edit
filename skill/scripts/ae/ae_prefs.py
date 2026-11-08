"""Pin the AE 25.6 render prefs before every aerender call: Multi-Frame Rendering OFF, disk cache OFF.
The AE GUI rewrites the prefs file on quit (it drops the Concurrent Frame Rendering section = MFR on, and
re-enables the disk cache); with MFR on, Sapphire S_Sharpen under the caption layers committed 13-19 GB."""
import os, sys
# AE 2025 (25.x) on Windows; override with CLIP_AE_PREFS=<path to 'Adobe After Effects <ver> Prefs.txt'>
P = os.environ.get('CLIP_AE_PREFS') or os.path.join(os.environ.get('APPDATA', ''), 'Adobe', 'After Effects', '25.6',
                                                  'Adobe After Effects 25.6 Prefs.txt')


def pin(mfr_off=True):
    s = open(P, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in s else '\n'
    s = s.replace('"Enabled 2" = "1"', '"Enabled 2" = "0"', 1)
    if '["Concurrent Frame Rendering"]' in s:
        s = s.replace('"Enable Concurrent Frame Renders" = 01', '"Enable Concurrent Frame Renders" = 00' if mfr_off else '"Enable Concurrent Frame Renders" = 01')
    elif mfr_off:
        sec = nl.join(['["Concurrent Frame Rendering"]', '\t"Enable Concurrent Frame Renders" = 00',
                       '\t"Number of Concurrent Frame Renders" = "1"', '\t"Reserved CPU Power" = "10"', '', ''])
        k = s.find('["Debug Prefs"]')
        s = s[:k] + sec + s[k:] if k >= 0 else s + nl + sec
    open(P, 'w', encoding='utf-8', newline='').write(s)
    ok = '"Enable Concurrent Frame Renders" = 00' in s and '"Enabled 2" = "0"' in s
    return ok


if __name__ == '__main__':
    print('prefs pinned' if pin() else 'PREFS NOT PINNED'); sys.exit(0)
