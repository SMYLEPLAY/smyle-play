# ─────────────────────────────────────────────────────────────────────────────
# SMYLE PLAY — agents/
# Chaîne autonome WATT : classification ADN → playlist → prompt Suno
#
# Pipeline :
#   upload track → dna_classifier → playlist_manager → suno_prompt_architect
#                                                     ↑
#                                              orchestrator.process_track()
# ─────────────────────────────────────────────────────────────────────────────

from .orchestrator import process_track

__all__ = ['process_track']
