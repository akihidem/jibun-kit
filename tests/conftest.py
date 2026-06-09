"""Shared pytest fixtures.

The payoff of de-globalizing common.py: tests inject a tmp workspace, so nothing
touches the real ~/Projects/jibun or needs $JIBUN_ROOT.
"""

import pytest

from jibun_kit.workspace import Workspace


@pytest.fixture
def tmp_workspace(tmp_path):
    ws = Workspace(tmp_path)
    ws.data_root.mkdir(parents=True, exist_ok=True)
    ws.sources_root.mkdir(parents=True, exist_ok=True)
    return ws
