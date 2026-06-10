from jibun_kit.ingest import REGISTRY, SourceGuide, load_source


def test_every_source_exports_guide():
    for name in REGISTRY:
        guide = getattr(load_source(name), "GUIDE", None)
        assert isinstance(guide, SourceGuide), f"{name}: GUIDE が無い"
        assert guide.label and guide.captures and guide.how_to_get, name


def test_guide_contract_shape():
    for name in REGISTRY:
        guide = load_source(name).GUIDE
        assert set(guide.path_flags) <= {"file", "dir"}, name
        assert all(flag.startswith("--") for flag in guide.path_flags.values()), name
        assert all(ask in {"date_range", "urls"} for ask in guide.asks), name
        for key in guide.identity_keys:
            section, _, leaf = key.rpartition(".")
            assert section and leaf, f"{name}: identity_key '{key}' はドット表記であること"


def test_fetch_extra_flagged_for_web_sources():
    assert load_source("twilog").GUIDE.needs_fetch_extra
    assert load_source("blog").GUIDE.needs_fetch_extra
    assert not load_source("claude-code").GUIDE.needs_fetch_extra
