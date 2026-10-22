# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit teaching fixtures, never browser-selected authority."""

LEGACY = (
    "info511-lab3-q4-synthetic",
    "info511-lab3-q4-synthetic-v1",
    "info511-hints-v1",
)
NHANES = (
    "info511-nhanes-wrangling",
    "info511-nhanes-wrangling-v1",
    "info511-nhanes-hints-v1",
)
SUPPORTED = frozenset((LEGACY, NHANES))
EXERCISE, VERSION, POLICY = NHANES
