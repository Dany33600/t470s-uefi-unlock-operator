"""
Extraction du Serial Number et infos BIOS depuis un dump T470s.

Approche par scoring pour fiabilite maximale :
- Chaque candidat SN est score selon plusieurs criteres
- Le SN avec le score le plus eleve est selectionne
- Si tous les scores sont faibles, on signale une faible confiance
"""
import re
import hashlib
from collections import Counter
from pathlib import Path


# Pattern SN ThinkPad : 2 lettres + chiffre + 5 chars alphanum
SN_PREFIX_PATTERN = rb'[A-Z]{2}[0-9][A-Z0-9]{5}'

# Pattern version BIOS Lenovo (ex: N1WET41W, N1QET94W)
BIOS_VERSION_PATTERN = rb'N1[A-Z]{2}[A-Z][0-9]{2}[A-Z]'

# Pattern Machine Type Model (ex: 20JTS2QA00)
MTM_PATTERN = rb'20[A-Z0-9]{8}'

# Marqueurs produits Lenovo (proximite = signal fort)
PRODUCT_MARKERS = [
    rb'ThinkPad T470', rb'ThinkPad T440', rb'ThinkPad T450',
    rb'ThinkPad T460', rb'ThinkPad T480',
    rb'ThinkPad X1', rb'ThinkPad X220', rb'ThinkPad X230',
    rb'ThinkPad X240', rb'ThinkPad X250', rb'ThinkPad X260',
    rb'ThinkPad X270', rb'ThinkPad',
]


def _score_sn_candidate(data: bytes, sn: bytes, offset: int) -> int:
    """Score de confiance pour un candidat SN."""
    score = 0
    
    # Critere 1 : isolement (entoure de \x00 ou \xFF)
    before = data[max(0, offset - 1):offset]
    after = data[offset + len(sn):offset + len(sn) + 1]
    if before in (b'\x00', b'\xff', b''):
        score += 5
    if after in (b'\x00', b'\xff', b''):
        score += 5
    
    # Critere 2 : prefixe Lenovo T470s courant
    sn_str = sn.decode('ascii', errors='ignore')
    if sn_str.startswith(('PC0', 'PF0', 'PF1', 'PF2', 'R9', 'MP1', 'LR')):
        score += 5
    
    # Critere 3 : proximite avec un marqueur produit (< 512 bytes avant)
    window_start = max(0, offset - 512)
    window = data[window_start:offset]
    for marker in PRODUCT_MARKERS:
        if marker in window:
            score += 20
            break
    
    # Critere 4 : detection de faux positifs (table de polices/glyphes)
    # Pattern type "P9Q9R9S9T9" = sequence de paires lettre+chiffre
    extended = data[max(0, offset - 8):offset + len(sn) + 8]
    if re.search(rb'([A-Z][0-9]){4,}', extended):
        score -= 30
    
    return score


def extract_sn(rom_path: str) -> dict:
    """
    Extrait SN, MTM et version BIOS depuis un dump .rom.
    
    Returns:
        {
            'sn': str ou None,
            'mtm': str ou None,
            'bios_version': str ou None,
            'sn_candidates': [(sn, offset, score), ...],  # top 5
            'confidence': 'high' | 'medium' | 'low' | 'none',
        }
    """
    rom_path = Path(rom_path)
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM file not found: {rom_path}")
    
    data = rom_path.read_bytes()
    
    # ─── Candidats SN avec scoring ──────────────────────────────
    candidates = []
    seen = set()
    
    for match in re.finditer(SN_PREFIX_PATTERN, data):
        sn_bytes = match.group()
        offset = match.start()
        key = (sn_bytes, offset)
        if key in seen:
            continue
        seen.add(key)
        
        score = _score_sn_candidate(data, sn_bytes, offset)
        sn_str = sn_bytes.decode('ascii', errors='ignore')
        candidates.append((sn_str, offset, score))
    
    candidates.sort(key=lambda c: -c[2])
    
    # Selection du meilleur candidat
    primary_sn = None
    confidence = 'none'
    if candidates:
        best = candidates[0]
        if best[2] >= 20:
            primary_sn = best[0]
            confidence = 'high'
        elif best[2] >= 10:
            primary_sn = best[0]
            confidence = 'medium'
        elif best[2] >= 0:
            primary_sn = best[0]
            confidence = 'low'
    
    # ─── MTM ────────────────────────────────────────────────────
    mtm = None
    mtm_matches = list(re.finditer(MTM_PATTERN, data))
    if mtm_matches:
        mtm_counts = Counter(m.group().decode('ascii', errors='ignore')
                             for m in mtm_matches)
        mtm = mtm_counts.most_common(1)[0][0]
    
    # ─── Version BIOS ───────────────────────────────────────────
    bios_version = None
    # Pattern fiable : version + espace + (x.xx)
    m = re.search(BIOS_VERSION_PATTERN + rb'\s*\([0-9]', data)
    if m:
        v_match = re.match(BIOS_VERSION_PATTERN, m.group())
        if v_match:
            bios_version = v_match.group().decode('ascii', errors='ignore')
    
    # Fallback : premiere occurrence
    if not bios_version:
        m = re.search(BIOS_VERSION_PATTERN, data)
        if m:
            bios_version = m.group().decode('ascii', errors='ignore')
    
    return {
        'sn': primary_sn,
        'mtm': mtm,
        'bios_version': bios_version,
        'sn_candidates': candidates[:5],
        'confidence': confidence,
    }


def md5_of_file(file_path: str) -> str:
    h = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sn_extractor.py <rom_file>")
        sys.exit(1)
    
    result = extract_sn(sys.argv[1])
    print(f"SN: {result['sn']} (confiance: {result['confidence']})")
    print(f"MTM: {result['mtm']}")
    print(f"BIOS: {result['bios_version']}")
    print(f"MD5: {md5_of_file(sys.argv[1])}")
    print(f"\nTop 5 candidats SN :")
    for sn, offset, score in result['sn_candidates']:
        print(f"  {sn:10s} @ 0x{offset:08x}  score={score}")
