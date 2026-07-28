"""Shared security primitives: envelope encryption and the egress guard.

Shared because both sides need them and two implementations would drift:
apps/api writes credentials, apps/worker resolves them at tool-call time,
and a second envelope format is ciphertext one service cannot read.
"""
