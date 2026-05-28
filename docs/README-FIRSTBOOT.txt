NoemaForge MVP Firstboot (v0.27.2)

Goal:
- Bootstrap NoemaForge on the real Debian Trixie host.
- Keep ToolProxy as the single tool entrypoint.
- Keep epoch changes pre-start only.
- Build model scorecards on the target machine instead of on Windows.

Recommended flow:
1) Prepare Windows-side metadata (optional but recommended):
   - tools\windows\Export-NoemaForge-E-Vault-Metadata.ps1
   - tools\windows\Export-NoemaForge-E-Compare-Metadata.ps1
   - tools\windows\Check-NoemaForge-VaultRoot.ps1
2) Install Debian Trixie (GUI session recommended for AV/voice/browser work).
3) Mount NOEMAFORGE_SHARE as /mnt/noemaforge-share.
4) Run the flattened-layout bootstrap command from docs/ONE_LINER.txt.
5) After bootstrap, run:

   sudo bash /opt/noemaforge/tools/prep/noemaforge-firstboot-from-share.sh \
     --share-root /mnt/noemaforge-share \
     --vault-root /mnt/noemaforge-share/noemaforge-lab/data/Vault \
     --top-k 2

6) Validate:

   sudo bash /opt/noemaforge/tools/prep/noemaforge-firstboot-smoke.sh

7) Review the newest draft request in PRE-START and approve it.

Notes:
- If the real E:\Vault export is empty for NoemaForge scanners, prefer the lab Vault on first boot.
- The helper writes a draft pre-start request; it does not mutate the active epoch directly.
- Administrator-path scorecards are added explicitly via dev.work / solution_architect.
