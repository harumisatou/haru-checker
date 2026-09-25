import zipfile
import io
import os
import re

def create_result_zip(valid_blocks, hold_blocks, valid_infos, hold_infos):
    """Create ZIP structure like bot di ss:
    Premium Hits/ -> premium accounts
    Normal Hits/ -> standard/basic etc
    _SUMMARY.txt
    Also returns raw txts for telegram files
    """
    mem=io.BytesIO()
    premium_count=0
    normal_count=0
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as z:
        # classify
        for idx, (block, info) in enumerate(zip(valid_blocks, valid_infos)):
            plan=(info.get("localizedPlanName") or "").lower()
            is_premium="premium" in plan or "ultra" in plan or "4k" in plan
            folder="Premium Hits" if is_premium else "Normal Hits"
            if is_premium: premium_count+=1
            else: normal_count+=1
            country=(info.get("countryOfSignup") or "XX").upper().strip() or "XX"
            country=country.replace(" ", "_")
            email_prefix=(info.get('email') or 'unknown').split('@')[0].replace(" ", "_")[:20]
            fname=f"{folder}/{idx+1:03d}_{country}_{email_prefix}.txt"
            content=block + "\n\nRaw Cookie:\n" + block.split("Cookie:")[-1]
            # simpler: just block
            z.writestr(fname, block)
        # also holds -> put in Normal? but we separate hold files not in this zip, valid zip only for hits
        summary=f"Premium Hits » {premium_count}\nNormal Hits » {normal_count}\nTotal » {premium_count+normal_count}\n\nZIP structure:\nPremium Hits/ — Premium account files\nNormal Hits/ — Standard / Basic / other files\n_SUMMARY.txt — Overview\n\nEach file: full details • cookie • login link\n"
        # add summary
        z.writestr("_SUMMARY.txt", summary)
    mem.seek(0)
    return mem.getvalue(), premium_count, normal_count

def build_valid_txt(blocks):
    return "\n\n".join(blocks) if blocks else "No valid accounts"

def build_hold_txt(blocks):
    return "\n\n".join(blocks) if blocks else "No on-hold accounts"

def build_invalid_txt(invalid_entries):
    # invalid_entries: list of (cookie_str, error)
    lines=[]
    for c,err in invalid_entries:
        lines.append(c + f"  # {err}")
    return "\n".join(lines) if lines else "No invalid cookies"
